# -*- coding: utf-8 -*-
import logging
import struct
from copy import deepcopy
from datetime import time, date, datetime, timezone
from decimal import Decimal as D
from typing import Union

from django.core.paginator import InvalidPage, Paginator
from django.db.models import Case, When, Value as V, Q, F
from django.db.models.constants import LOOKUP_SEP
from django.db.models.expressions import OrderBy
from django.http import Http404
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.translation import gettext_lazy as _

from . import constants


logger = logging.getLogger(__name__)


class SerializationError(RuntimeError):
	pass


def is_short_string(v) -> bool:
	return isinstance(v, str) and len(v.encode('utf-8')) < 320


def serialize_short_string(v: str) -> bytes:
	v = v.encode('utf-8')
	return struct.pack('B', len(v) - 64) + v


def deserialize_short_string(v: bytes) -> tuple:
	length = v[0] + 64
	text = v[1:length + 1].decode('utf-8')
	return length + 1, text


def is_long_string(v) -> bool:
	if not isinstance(v, str):
		return False
	v = v.encode('utf-8')
	if len(v) > (65535+320):
		raise SerializationError("String value too long")
	return True


def serialize_long_string(v: str) -> bytes:
	v = v.encode('utf-8')
	length = len(v) - 320
	return struct.pack('!H', length) + v


def deserialize_long_string(v: bytes) -> tuple:
	length = struct.unpack('!H', v[:2])[0] + 320
	return length + 2, v[2:length + 2].decode('utf-8')


def is_bytes(v) -> bool:
	return isinstance(v, bytes)


def serialize_bytes(v: bytes) -> bytes:
	if len(v) > 65535:
		raise SerializationError("Bytes value too long")
	return struct.pack('!H', len(v)) + v


def deserialize_bytes(v: bytes) -> tuple:
	length = struct.unpack('!H', v[:2])[0]
	return length + 2, v[2:]


NUMBER_SIZES = [1, 2, 4, 8]
NUMBER_FORMATS = ['B', '!H', '!I', '!Q']
NUMBER_MAX_VALUES = [sum(256**s for s in NUMBER_SIZES[0:size+1]) for size in range(4)]
NUMBER_SUBTRACTS = [0] + NUMBER_MAX_VALUES[:-1]


def number_serializer(size_idx, number_type):
	negative = size_idx < 0
	size_idx = abs(size_idx) - 1
	size = NUMBER_SIZES[size_idx]

	max_val = NUMBER_MAX_VALUES[size_idx]
	subtract = NUMBER_SUBTRACTS[size_idx]

	if negative:
		max_val += 1

	def match(val):
		if not isinstance(val, number_type):
			return False
		if isinstance(val, D) and val.to_integral_value() != val:
			return False
		if negative:
			val = -val
		return val >= 0 and val < max_val

	def serialize(val):
		val = val
		if negative:
			val = -val - 1
		val = val - subtract
		if isinstance(val, D):
			val = int(val.to_integral_value())
		return struct.pack(NUMBER_FORMATS[size_idx], val)

	def deserialize(val):
		val = struct.unpack(NUMBER_FORMATS[size_idx], val[:size])[0] + subtract
		if negative:
			val = -val - 1
		return size, number_type(val)

	return (match, serialize, deserialize)


def serialize_long_number(val: Union[int, D]) -> bytes:
	val = str(val).encode('utf-8')
	if len(val) < 255:
		return struct.pack('B', len(val)) + val
	else:
		return struct.pack('B', 255) + struct.pack('!H', len(val) - 255) + val


def deserialize_long_number_type(val: bytes, number_type: type) -> tuple:
	header_size = 1
	length = val[0]
	if length == 255:
		length = struct.unpack('!H', val[1:3])[0] + 255
		header_size = 3
	num = number_type(val[header_size:header_size+length].decode('utf-8'))
	return (length + header_size, num)


def deserialize_long_number(val: bytes) -> tuple:
	return deserialize_long_number_type(val, int)


def deserialize_long_decimal(val: bytes) -> D:
	return deserialize_long_number_type(val, D)


def serialize_time(val: time) -> bytes:
	num = val.second + val.minute * 60 + val.hour * 3600
	if val.microsecond == 0:
		num = struct.pack('!I', num)
		return num[-3:] # only 3 bytes needed
	else:
		num = num * 1000000 + val.microsecond + (2 ** 39)
		num = struct.pack('!Q', num)
		return num[-5:] # only 3 bytes needed


def deserialize_time(val: bytes) -> tuple:
	first = val[0]
	microseconds = 0
	if first < 128: # without microseconds
		length = 3
		val = b'\x00' + val[:3]
		num = struct.unpack('!I', val)[0]
	else:
		length = 5
		val = b'\x00\x00\x00' + val[:5]
		num = struct.unpack('!Q', val)[0]
		num &= 0x7fffffffff
		microseconds = num % 1000000
		num = num // 1000000
	val = time(num // 3600, (num // 60) % 60, num % 60, microseconds)
	return (length, val)


def date_serializer(use_timezone: bool, use_microsecond: bool) -> tuple:
	def match(value: datetime) -> bool:
		if not isinstance(value, datetime):
			return False
		has_timezone = value.tzinfo is not None
		has_microsecond = value.microsecond != 0
		return has_timezone == use_timezone and has_microsecond == use_microsecond

	def serialize(val: datetime) -> bytes:
		if val.tzinfo:
			val = val.astimezone(timezone.utc)

		timestamp = (val.date().toordinal() - 719163) * 86400
		timestamp += val.time().hour * 3600 + val.time().minute * 60 + val.time().second

		julian_timestamp = timestamp + 210866760000
		data = struct.pack('!Q', julian_timestamp)
		if use_microsecond:
			data += struct.pack('!I', val.microsecond)

		return data

	def deserialize(val: bytes) -> tuple:
		timestamp = struct.unpack('!Q', val[0:8])[0] - 210866760000
		value = datetime.utcfromtimestamp(timestamp)
		if use_timezone:
			value = value.replace(tzinfo=timezone.utc)
		if use_microsecond:
			value = value.replace(microsecond=struct.unpack('!I', val[8:12])[0])

		return (12 if use_microsecond else 8, value)

	return (match, serialize, deserialize)



VALUE_SERIALIZERS = [
	(lambda v: v is None, lambda v: b'', lambda v: (0, None)),
	(lambda v: v is True, lambda v: b'', lambda v: (0, True)),
	(lambda v: v is False, lambda v: b'', lambda v: (0, False)),
	(is_short_string, serialize_short_string, deserialize_short_string),
	(is_long_string, serialize_long_string, deserialize_long_string),
	(is_bytes, serialize_bytes, deserialize_bytes),
	number_serializer(1, int), # one_byte
	number_serializer(-1, int), # one_byte negative
	number_serializer(2, int), # two bytes positive
	number_serializer(-2, int), # two bytes negative
	number_serializer(3, int), # four bytes positive
	number_serializer(-3, int), # four bytes negative
	number_serializer(4, int), # eight bytes positive
	number_serializer(-4, int), # eight bytes negative
	(lambda v: isinstance(v, int), serialize_long_number, deserialize_long_number),
	number_serializer(1, D), # one_byte
	number_serializer(-1, D), # one_byte negative
	number_serializer(2, D), # two bytes positive
	number_serializer(-2, D), # two bytes negative
	number_serializer(3, D), # four bytes positive
	number_serializer(-3, D), # four bytes negative
	number_serializer(4, D), # eight bytes positive
	number_serializer(-4, D), # eight bytes negative
	(lambda v: isinstance(v, D) and v.to_integral_value() == v, serialize_long_number, deserialize_long_decimal),
	(lambda v: isinstance(v, float), lambda v: struct.pack('!d', v), lambda v: (8, struct.unpack('!d', v[:8])[0])),
	(lambda v: isinstance(v, D), serialize_long_number, deserialize_long_decimal),
	date_serializer(use_timezone=False, use_microsecond=False),
	date_serializer(use_timezone=False, use_microsecond=True),
	date_serializer(use_timezone=True, use_microsecond=False),
	date_serializer(use_timezone=True, use_microsecond=True),
	(lambda v: isinstance(v, time), serialize_time, deserialize_time),
	(lambda v: isinstance(v, date), lambda v: struct.pack('!I', v.toordinal() + 1721424), lambda v: (4, date.fromordinal(struct.unpack('!I', v[:4])[0] - 1721424))), # from julian date
]
"""
List of (check function, serialize function, deserialize function)
"""


def paginate_queryset(queryset, page, page_size):
	"""
	Shortcut to paginate queryset
	"""
	paginator = Paginator(queryset, page_size)
	try:
		page_number = int(page)
	except ValueError:
		raise Http404(_("Page is not number."))

	try:
		page = paginator.page(page_number)
		return (paginator, page, page.object_list, page.has_other_pages())
	except InvalidPage as e:
		raise Http404(_('Invalid page (%(page_number)s): %(message)s') % {'page_number': page_number, 'message': str(e)})


def get_model_attribute(obj, attribute):
	"""
	Get model attribute by traversing attributes by django path like review__book
	"""
	for lookup in attribute.split(LOOKUP_SEP):
		obj = getattr(obj, lookup)
	return obj


def get_order_key(obj, order_by):
	"""
	Get list of attributes for order key, e.g. if order_key is ['pk'], it will
	return [obj.pk]
	"""
	return tuple(
		get_model_attribute(obj, f.expression.name if isinstance(f, OrderBy) else f.lstrip('-'))
		for f in order_by
	)


def serialize_value(value) -> bytes:
	if isinstance(value, str) and len(value.encode('utf-8')) < 64:
		value = value.encode('utf-8')
		return struct.pack('B', 192 + len(value)) + value

	for i, serializer in enumerate(VALUE_SERIALIZERS):
		checker, serializer, __ = serializer
		if checker(value):
			return struct.pack('B', i) + serializer(value)
	return serialize_value(str(value))


def serialize_values(values: list) -> bytes:
	return b''.join(serialize_value(value) for value in values)


def deserialize_values(data: bytes) -> list:
	values = []
	while data:
		data_type, data = data[0], data[1:]
		if data_type >= 192:
			string_length = data_type - 192
			values.append(data[:string_length].decode('utf-8'))
			data = data[string_length:]
		else:
			consumed, value = VALUE_SERIALIZERS[data_type][2](data)
			if consumed:
				data = data[consumed:]
			values.append(value)
	return values


def url_decode_order_key(order_key):
	"""
	Encode list of order keys to URL string
	"""
	return tuple(deserialize_values(urlsafe_base64_decode(order_key)))


def url_encode_order_key(value):
	"""
	Decode list of order keys from URL string
	"""
	# prevent microsecond clipping
	return urlsafe_base64_encode(serialize_values(value))


def get_order_by(qs):
	"""
	Returns order_by from queryset
	"""
	query = qs.query
	return query.order_by or query.get_meta().ordering


def invert_order_by(order_by):
	"""
	Invert list of OrderBy expressions
	"""
	order_by = deepcopy(order_by)
	for field in order_by:
		# invert asc / desc
		field.descending = not field.descending

		# invert nulls first / last (only one can be active)
		if field.nulls_first:
			field.nulls_first = None
			field.nulls_last = True
		elif field.nulls_last:
			field.nulls_last = None
			field.nulls_first = True

	return order_by


def convert_to_order_by(field):
	"""
	Converts field name to OrderBy expression
	"""
	if isinstance(field, OrderBy):
		return field
	return F(field[1:]).desc() if field[:1] == '-' else F(field).asc()


def convert_order_by_to_expressions(order_by):
	"""
	Converts list of order_by keys like ['pk'] to list of OrderBy objects
	"""
	return [convert_to_order_by(field) for field in order_by]


def filter_by_order_key(qs, direction, start_position):
	"""
	Filter queryset from specific position inncluding start position
	"""

	# change list of strings or expressions to list of expressions
	order_by = convert_order_by_to_expressions(get_order_by(qs))

	# check if we have required start_position
	if len(start_position) != len(order_by):
		raise InvalidPage()

	# invert order
	if direction == constants.KEY_BACK:
		order_by = invert_order_by(order_by)
		qs = qs.order_by(*order_by)

	filter_combinations = {}
	q = Q() # final filter

	# create chain of rule rule for example for name="x" parent=1, id=2 will be following:
	# name > 'x' OR name = 'x' AND parent > 1 OR name = 'x' AND parent = 1 AND id >= 2
	for i, value in enumerate(zip(order_by, start_position)):
		# unpack values
		order_expression, value = value

		# last tieration
		is_last = i == len(order_by) - 1

		# filter by
		field_name = order_expression.expression.name

		field_lookup = ''

		# Value  Order (NULL)  First condition    Next condition
		# ------------------------------------------------------
		# Val    Last          >< Val | NULL      =Val
		# Val    First         >< Val             =Val
		# NULL   Last          SKIP               =NULL
		# NULL   First         NOT NULL           =NULL

		if value is None: # special NULL handling
			if order_expression.nulls_last:
				field_lookup = f'{field_name}__isnull'
				filter_combinations[field_lookup] = True
				continue
			if order_expression.nulls_first:
				filter_combinations[f'{field_name}__isnull'] = False
				q |= Q(**filter_combinations)
				filter_combinations[f'{field_name}__isnull'] = True
				continue
			else:
				logger.warning("No nulls_first / nulls_last specified")
		else:
			# smaller or greater
			direction = 'lt' if order_expression.descending else 'gt'
			if is_last: # change > to >= and < to <= on last iteration
				direction = f'{direction}e'

			# construct field lookup
			field_lookup = f'{field_name}__{direction}'

			# set lookup to current combination
			if order_expression.nulls_last:
				filter_combination = (
					Q(**filter_combinations) &
					(Q(**{field_lookup: value}) | Q(**{f'{field_name}__isnull': True}))
				)
				q |= filter_combination
				filter_combinations[field_name] = value
				continue
			else:
				filter_combinations[field_lookup] = value

		# apply combination
		filter_combination = Q(**filter_combinations)
		q |= filter_combination

		# transform >, < to equals
		filter_combinations.pop(field_lookup, None)
		filter_combinations[field_name] = value

	# apply filter
	if q:
		try:
			qs = qs.filter(q)

			# mark item which matches start position
			sentinel_query = {
				order_expression.expression.name: start
				for order_expression, start
				in zip(order_by, start_position)
			}
			is_sentinel = Case(
				When(Q(**sentinel_query), then=V(True)),
				default=V(False)
			)
			sentinel_annotation = {
				constants.SENTINEL_NAME: is_sentinel
			}
			qs = qs.annotate(**sentinel_annotation)
		except Exception:
			raise InvalidPage()

	return qs
