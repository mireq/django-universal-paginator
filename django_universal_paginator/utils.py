# -*- coding: utf-8 -*-
import datetime
import json
import logging
import struct
from copy import deepcopy

from django.db.models import Case, When, Value as V
from django.core.paginator import InvalidPage, Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q, F
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
	return isinstance(v, str) and len(v) < 256


def serialize_short_string(v: str) -> bytes:
	return struct.pack('B', len(v)) + v.encode('utf-8')


def deserialize_short_string(v: bytes) -> tuple:
	length = v[0]
	text = v[1:].decode('utf-8')
	return length + 1, text


def is_long_string(v) -> bool:
	if not isinstance(v, str):
		return False
	if len(v) > (65535+256):
		raise SerializationError("String value too long")
	return True


def serialize_long_string(v: str) -> bytes:
	length = len(v) - 256
	return struct.pack('!H', length) + v.encode('utf-8')


def deserialize_long_string(v: bytes) -> tuple:
	length = struct.unpack('!H', v[:2])[0] + 256
	return length + 2, v[2:].decode('utf-8')


def is_bytes(v) -> bool:
	return isinstance(v, bytes)


def serialize_bytes(v: bytes) -> bytes:
	if len(v) > 65535:
		raise SerializationError("Bytes value too long")
	return struct.pack('!H', len(v)) + v


def deserialize_bytes(v: bytes) -> tuple:
	length = struct.unpack('!H', v[:2])[0]
	return length + 2, v[2:]


def integer_serializer(size_idx):
	negative = size_idx < 0
	size_idx = abs(size_idx) - 1
	sizes = [1, 2, 4, 8]
	size = sizes[size_idx]
	formats = ['B', '!H', '!I', '!Q']

	max_val = 0
	subtract = 0
	for step in sizes[:size_idx + 1]:
		subtract = max_val
		max_val += (256 ** step)

	if negative:
		max_val += 1

	def match(val):
		if not isinstance(val, int):
			return False
		if negative:
			val = -val
		return val >= 0 and val < max_val

	def serialize(val):
		val = val
		if negative:
			val = -val - 1
		return struct.pack(formats[size_idx], val - subtract)

	def deserialize(val):
		val = struct.unpack(formats[size_idx], val[:size])[0] + subtract
		if negative:
			val = -val - 1
		return size, val

	return (match, serialize, deserialize)



VALUE_SERIALIZERS = [
	(lambda v: v is None, lambda v: b'', lambda v: (0, None)),
	(lambda v: v is True, lambda v: b'', lambda v: (0, True)),
	(lambda v: v is False, lambda v: b'', lambda v: (0, False)),
	(is_short_string, serialize_short_string, deserialize_short_string),
	(is_long_string, serialize_long_string, deserialize_long_string),
	(is_bytes, serialize_bytes, deserialize_bytes),
	integer_serializer(1), # one_byte
	integer_serializer(-1), # one_byte negative
	integer_serializer(2), # two bytes positive
	integer_serializer(-2), # two bytes negative
	integer_serializer(3), # four bytes positive
	integer_serializer(-3), # four bytes negative
	integer_serializer(4), # eight bytes positive
	integer_serializer(-4), # eight bytes negative
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
		consumed, value = VALUE_SERIALIZERS[data_type][2](data)
		if consumed:
			data = data[consumed:]
		values.append(value)
	return values


def url_decode_order_key(order_key):
	"""
	Encode list of order keys to URL string
	"""
	return tuple(json.loads(urlsafe_base64_decode(order_key).decode('utf-8')))


def values_to_order_key(value):
	"""
	Convert values to serializable format
	"""
	return tuple(v.isoformat() if isinstance(v, datetime.datetime) else v for v in value)


def url_encode_order_key(value):
	"""
	Decode list of order keys from URL string
	"""
	# prevent microsecond clipping
	return urlsafe_base64_encode(json.dumps(values_to_order_key(value), cls=DjangoJSONEncoder).encode('utf-8'))


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
