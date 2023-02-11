# -*- coding: utf-8 -*-
from datetime import datetime, time, date

from django.core.paginator import InvalidPage
from django.db.models import F
from django.http import Http404
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal as D

from .models import Book, BookOrdered, Review
from django_universal_paginator import constants
from django_universal_paginator.converter import PageConverter, CursorPageConverter
from django_universal_paginator.cursor import paginate_cursor_queryset, CursorPaginateMixin
from django_universal_paginator.utils import paginate_queryset, get_model_attribute, get_order_key, url_encode_order_key, url_decode_order_key, get_order_by, invert_order_by, convert_to_order_by, convert_order_by_to_expressions, filter_by_order_key, serialize_value, serialize_values, deserialize_values, SerializationError


class CursorPaginatedView(CursorPaginateMixin):
	page_kwarg = 'page'
	kwargs = {'page': 1}


class TestPageConverter(TestCase):
	def test_to_pyton(self):
		converter = PageConverter()
		self.assertEqual(1, converter.to_python('')) # empty
		self.assertEqual(2, converter.to_python('2'))
		self.assertEqual(2, converter.to_python('2/'))

	def test_to_url(self):
		converter = PageConverter()
		self.assertEqual('', converter.to_url('')) # empty
		self.assertEqual('', converter.to_url(1)) # first page ommited
		self.assertEqual('', converter.to_url('1')) # compatible with strings
		self.assertEqual('2/', converter.to_url('2'))

	def test_urlconf(self):
		self.assertEqual('/page/', reverse('page', kwargs={'page': 1}))
		self.assertEqual('/page/', reverse('page', kwargs={'page': '1'}))
		self.assertEqual('/page/2/', reverse('page', kwargs={'page': 2}))
		self.assertEqual('/page/2/', reverse('page', kwargs={'page': '2'}))

	def test_cursor_to_pyton(self):
		converter = CursorPageConverter()
		self.assertEqual(1, converter.to_python('')) # empty
		self.assertEqual('nabc', converter.to_python('nabc'))

	def test_cursor_to_url(self):
		converter = CursorPageConverter()
		self.assertEqual('', converter.to_url('')) # empty
		self.assertEqual('', converter.to_url(1)) # first page ommited
		self.assertEqual('nabc/', converter.to_url('nabc'))

	def test_cursor_urlconf(self):
		self.assertEqual('/cursor/nabc/', reverse('cursor_page', kwargs={'page': 'nabc'}))


class TestUtils(TestCase):
	def test_paginate_queryset(self):
		books = [Book(name="1"), Book(name="2"), Book(name="3")]
		Book.objects.bulk_create(books)
		qs = Book.objects.order_by('pk')
		books = list(qs)

		with self.assertRaises(Http404):
			paginate_queryset(qs, page="invalid", page_size=2)

		with self.assertRaises(Http404):
			paginate_queryset(qs, page=20, page_size=2)

		paginator, page, object_list, has_others = paginate_queryset(qs, page=2, page_size=2)

		self.assertEqual(2, paginator.per_page)
		self.assertTrue(page.has_previous())
		self.assertFalse(page.has_next())
		self.assertEqual(3, page.end_index())
		self.assertEqual(books[2:], list(object_list))
		self.assertTrue(has_others)

	def test_get_model_attribute(self):
		book = Book.objects.create(name="book")
		review = Review.objects.create(book=book, text="review")

		self.assertEqual("review", get_model_attribute(review, "text"))
		self.assertEqual("book", get_model_attribute(review, "book__name"))

	def test_get_order_key(self):
		book = Book.objects.create(name="book")
		review = Review.objects.create(book=book, text="review")

		# simple case
		self.assertEqual(
			(book.pk,),
			get_order_key(book, ['pk'])
		)

		# negative are supported too
		self.assertEqual(
			(book.pk,),
			get_order_key(book, ['-pk'])
		)

		# f expression
		self.assertEqual(
			(book.pk,),
			get_order_key(book, [F('pk').desc()])
		)

		# multiple values
		self.assertEqual(
			(review.pk, review.book_id, review.book.name),
			get_order_key(review, ['pk', 'book_id', 'book__name'])
		)

	def test_get_order_by(self):
		# simple case
		qs = Book.objects.order_by('name', 'pk')
		self.assertEqual(('name', 'pk'), get_order_by(qs))

		# default ordering
		qs = BookOrdered.objects.all()
		self.assertEqual(('pk',), get_order_by(qs))

	def test_encode_order_key(self):
		# empty
		order_key = ()
		self.assertEqual(order_key, url_decode_order_key(url_encode_order_key(order_key)))

		# single value
		order_key = (1,)
		self.assertEqual(order_key, url_decode_order_key(url_encode_order_key(order_key)))

		# None
		order_key = (None,)
		self.assertEqual(order_key, url_decode_order_key(url_encode_order_key(order_key)))

		# different values
		order_key = (1, "text")
		self.assertEqual(order_key, url_decode_order_key(url_encode_order_key(order_key)))

		# datetime
		order_key = (timezone.now(),)
		processed_order_key = url_decode_order_key(url_encode_order_key(order_key))
		self.assertEqual(order_key, processed_order_key)

	def test_invert_order_by(self):
		order_by = [F('name').asc()]
		inverted = [F('name').desc()]
		self.assertOrderByEqual(inverted[0], invert_order_by(order_by)[0])

		order_by = [F('name').desc()]
		inverted = [F('name').asc()]
		self.assertOrderByEqual(inverted[0], invert_order_by(order_by)[0])

		order_by = [F('name').asc(nulls_first=True)]
		inverted = [F('name').desc(nulls_last=True)]
		self.assertOrderByEqual(inverted[0], invert_order_by(order_by)[0])

		order_by = [F('name').asc(nulls_last=True)]
		inverted = [F('name').desc(nulls_first=True)]
		self.assertOrderByEqual(inverted[0], invert_order_by(order_by)[0])

	def test_convert_order_by_to_expressions(self):
		e = convert_to_order_by('pk')
		self.assertEqual(e.expression.name, 'pk')
		self.assertFalse(e.descending)

		e = convert_to_order_by('-pk')
		self.assertEqual(e.expression.name, 'pk')
		self.assertTrue(e.descending)

		# conversion not needed
		e = convert_to_order_by(F('pk').asc())
		self.assertEqual(e.expression.name, 'pk')

		e = convert_order_by_to_expressions(['pk'])
		self.assertEqual(e[0].expression.name, 'pk')
		self.assertFalse(e[0].descending)

	def assertOrderByEqual(self, a, b):
		self.assertTrue(a.descending == b.descending and bool(a.nulls_first) == bool(b.nulls_first) and bool(a.nulls_last) == bool(b.nulls_last))

	def test_filter_by_order_key(self):
		book_list = [
			Book(id=1, pub_time='1970-01-01T00:00:00', name="A"),
			Book(id=2, pub_time='1970-01-02T00:00:00', name="A", rating=3.0),
			Book(id=3, pub_time='1970-01-03T00:00:00', name="A", rating=2.0),
			Book(id=4, pub_time='1970-01-04T00:00:00', name="B"),
			Book(id=5, pub_time='1970-01-05T00:00:00', name="B"),
		]
		Book.objects.bulk_create(book_list)
		book_list = {b.pk: b for b in Book.objects.all()}

		def get_books(order, values=(), backwards=False, model=Book):
			direction = constants.KEY_BACK if backwards else constants.KEY_NEXT
			books = model.objects.order_by(*order).values_list('pk', flat=True)
			return list(filter_by_order_key(books, direction, values))

		with self.assertRaises(InvalidPage):
			books = get_books(['pk'], []) # missing parameter

		with self.assertRaises(InvalidPage):
			books = get_books(['pk'], ['x']) # wrong value

		# no nulls specified
		with self.assertLogs('django_universal_paginator.utils'):
			get_books([F('rating').asc(), 'pk'], [None, 1])

		# empty filter
		books = get_books([], [])
		self.assertEqual([1, 2, 3, 4, 5], books)

		def check_filter(order_by, backwards=False):
			books = list(Book.objects.order_by(*order_by))
			if backwards:
				books.reverse()
			ids = list(book.pk for book in books)
			expect_ids = ids
			next_book = ids[0]
			debug_books = '\n'.join(str(book) for book in books)

			while True:
				book = book_list[next_book]
				order_key = get_order_key(book, order_by)
				ids = get_books(order_by, order_key, backwards=backwards)
				self.assertEqual(expect_ids, ids, msg=f'Wrong rows returned, requested order: {order_by}, order_key: {order_key}, books:\n{debug_books}')
				expect_ids = ids[1:]
				if len(ids) < 2:
					break
				next_book = ids[1]

		def check_filters(order_by):
			check_filter(order_by)
			check_filter(order_by, backwards=True)

		check_filters(['pk'])
		check_filters(['-pk'])
		check_filters(['pub_time'])
		check_filters(['-pub_time'])
		check_filters(['name', 'pk'])
		check_filters(['name', '-pk'])
		check_filters(['-name', 'pk'])
		check_filters(['name', F('rating').asc(nulls_last=True), 'pk'])
		check_filters(['name', F('rating').asc(nulls_first=True), 'pk'])
		check_filters(['name', F('rating').desc(nulls_last=True), 'pk'])
		check_filters(['name', F('rating').desc(nulls_first=True), 'pk'])
		check_filters([F('rating').asc(nulls_last=True), 'pk'])
		check_filters([F('rating').asc(nulls_first=True), 'pk'])

		Book.objects.all().delete()
		book_list = [
			Book(id=1, pub_time='1970-01-01T00:00:00', name="A"),
			Book(id=2, pub_time='1970-01-02T00:00:00', name="A", is_published=False),
			Book(id=3, pub_time='1970-01-03T00:00:00', name="A", is_published=False, rating=3.0),
			Book(id=4, pub_time='1970-01-04T00:00:00', name="B", rating=2.0),
			Book(id=5, pub_time='1970-01-05T00:00:00', name="B"),
		]
		Book.objects.bulk_create(book_list)
		book_list = {b.pk: b for b in Book.objects.all()}

		check_filters(['is_published', 'pk'])
		check_filters(['is_published', '-pk'])
		check_filters(['name', F('rating').asc(nulls_last=True), 'pk'])
		check_filters(['name', F('rating').asc(nulls_first=True), 'pk'])
		check_filters(['name', F('rating').desc(nulls_last=True), 'pk'])
		check_filters(['name', F('rating').desc(nulls_first=True), 'pk'])
		check_filters([F('rating').asc(nulls_last=True), 'pk'])
		check_filters([F('rating').asc(nulls_first=True), 'pk'])


class TestCursorPaginator(TestCase):
	@classmethod
	def setUpTestData(cls):
		book_list = [
			Book(id=1, name="1"),
			Book(id=2, name="2"),
			Book(id=3, name="3"),
			Book(id=4, name="4"),
			Book(id=5, name="5"),
		]
		Book.objects.bulk_create(book_list)

	def test_invalid_page(self):
		qs = Book.objects.order_by('pk')
		with self.assertRaises(Http404):
			__ = paginate_cursor_queryset(qs, 'invalid', 2)
		with self.assertRaises(Http404):
			__ = paginate_cursor_queryset(qs, constants.KEY_BACK + 'invalid', 2)

	def test_first_page(self):
		qs = Book.objects.order_by('pk')
		__, __, qs, __ = paginate_cursor_queryset(qs, None, 2)
		self.assertBookPage([1, 2], qs)

	def test_empty(self):
		books = Book.objects.order_by('pk').none()
		__, page, qs, __ = paginate_cursor_queryset(books, None, 2)
		self.assertFalse(page.has_previous())
		self.assertFalse(page.has_next())
		self.assertBookPage([], qs)

	def test_paginate(self):
		books = Book.objects.order_by('pk')
		paginator, page, qs, __ = paginate_cursor_queryset(books, None, 2)
		# not needed
		self.assertEqual(0, paginator.count)
		self.assertEqual(0, paginator.num_pages)
		self.assertFalse(page.has_previous())
		self.assertTrue(page.has_next())

		# second page
		number = page.next_page_number()

		__, page, qs, __ = paginate_cursor_queryset(books, number, 2)
		self.assertTrue(page.has_previous())
		self.assertTrue(page.has_next())
		self.assertBookPage([3, 4], qs)

		# last page
		number = page.next_page_number()

		__, page, qs, __ = paginate_cursor_queryset(books, number, 2)
		self.assertTrue(page.has_previous())
		self.assertFalse(page.has_next())
		self.assertBookPage([5], qs)

		# again second page
		number = page.previous_page_number()

		__, page, qs, __ = paginate_cursor_queryset(books, number, 2)
		self.assertTrue(page.has_previous())
		self.assertTrue(page.has_next())
		self.assertBookPage([3, 4], qs)

		# again first page
		number = page.previous_page_number()

		__, page, qs, __ = paginate_cursor_queryset(books, number, 2)
		self.assertFalse(page.has_previous())
		self.assertTrue(page.has_next())
		self.assertBookPage([1, 2], qs)

		# check missing key
		Book.objects.filter(pk=3).delete()

		books = Book.objects.order_by('pk')
		__, page, qs, __ = paginate_cursor_queryset(books, number, 2)
		self.assertBookPage([1, 2], qs)

	def test_cbv(self):
		v = CursorPaginatedView()

		books = Book.objects.order_by('pk')

		__, __, qs, __ = v.paginate_queryset(books, page_size=2)
		self.assertBookPage([1, 2], qs)

	def assertBookPage(self, ids, qs):
		returned_pages = [obj.pk for obj in qs]
		self.assertEqual(ids, returned_pages)


class TestTemplates(TestCase):
	@classmethod
	def setUpTestData(cls):
		book_list = [
			Book(id=1, name="1"),
			Book(id=2, name="2"),
			Book(id=3, name="3"),
			Book(id=4, name="4"),
			Book(id=5, name="5"),
		]
		Book.objects.bulk_create(book_list)

	def test_simple_pagination(self):
		url = reverse('page', kwargs={'page': 1})
		response = self.client.get(url)
		self.assertContains(response, '/page/3/')
		self.assertContains(response, '/using-get/?page=3')

		response = self.client.get(f'{url}?engine=jinja')
		self.assertEqual(['example.jinja'], response.template_name)
		self.assertContains(response, '/page/3/')

	def test_cursor_pagination(self):
		url = reverse('cursor_page', kwargs={'page': 1})
		response = self.client.get(url)
		self.assertNotContains(response, '/page/3/')


class TestSerializer(TestCase):
	def test_serialize_none(self):
		val = serialize_value(None)
		# use single byte for None representation
		self.assertEqual(1, len(val))

		# concat two None values
		val = serialize_values([None, None])
		self.assertEqual(2, len(val))

		deserialized = deserialize_values(val)
		self.assertEqual([None, None], deserialized)

	def test_serialize_bool(self):
		value_list = [True, False]

		val = serialize_values(value_list)
		self.assertEqual(2, len(val)) # single byte for boolean
		deserialized = deserialize_values(val)
		self.assertEqual(value_list, deserialized)

	def test_serialize_text(self):
		texts = [
			('', 0), # zero size
			('hello 😼', len('hello 😼'.encode('utf-8'))), # unicode
			('x' * 63, 63), # max short size
			('x' * 64, 65), # second byte to specify size
			('x' * (64 + 256 - 1), 64 + 256), # max length with single addiional byte
			('x' * (64 + 256), 64 + 256 + 2), # two bytes required for size
			('x' * (64 + 256 + 65536 - 1), 64 + 256 + 65536 + 1), # maximum size
		]

		for expected_text, expected_size in texts:
			val = serialize_values([expected_text, expected_text])
			size = len(val) // 2 - 1
			deserialized = deserialize_values(val)
			self.assertEqual([expected_text, expected_text], deserialized)
			self.assertEqual(expected_size, size)

		text = 'x' * (64 + 256 + 65536) # too long
		with self.assertRaises(SerializationError):
			serialize_values([text])

	def test_serialize_bytes(self):
		text = b'x' * 500
		val = serialize_values([text])
		deserialized = deserialize_values(val)
		self.assertEqual(len(text) + 3, len(val))
		self.assertEqual([text], deserialized)

		text = b'x' * 65536 # too long
		with self.assertRaises(SerializationError):
			serialize_values([text])

	def test_serialize_unknown_object(self):
		text = 'hello'
		class UnknownObject(object):
			def __str__(self):
				return text

		# perform only string conversion
		val = serialize_values([UnknownObject()])
		deserialized = deserialize_values(val)
		self.assertEqual([text], deserialized)

	def test_serialize_integer(self):
		num_size_tests = [
			(0, 1), # single byte, min value
			(255, 1), # single byte, max value
			(-1, 1), # single byte min negative value
			(-256, 1), # single byte max negative value
			(256, 2), # two bytes, min value
			(256 + 65536 - 1, 2), # two bytes, max value
			(-256 - 1, 2), # two bytes, min negative value
			(-256 - 65536, 2), # two bytes, max negative value
			(256 + 65536, 4), # four bytes, min value
			(256 + 65536 + 4294967296 - 1, 4), # four bytes, max value
			(-256 - 65536 - 1, 4), # four bytes, min negative value
			(-256 - 65536 - 4294967296, 4), # four bytes, max negative value
			(256 + 65536 + 4294967296, 8), # eight bytes, min value
			(256 + 65536 + 4294967296 + 18446744073709551616 - 1, 8), # eight bytes, max value
			(-256 - 65536 - 4294967296 - 1, 8), # eight bytes, min negative value
			(-256 - 65536 - 4294967296 - 18446744073709551616, 8), # eight bytes, max negative value
			(256 + 65536 + 4294967296 + 18446744073709551616, 21), # positive, as string
			(-256 - 65536 - 4294967296 - 18446744073709551616 - 1, 22), # negative, as string
			(int('9' * 255), 258), # really big number
		]

		for expected_num, expected_size in num_size_tests:
			data = [expected_num, D(expected_num)]
			val = serialize_values(data)
			deserialized = deserialize_values(val)
			self.assertEqual(data, deserialized)
			self.assertEqual(2 * (expected_size + 1), len(val))

	def test_serialize_float(self):
		data = [0.1]
		val = serialize_values(data)
		deserialized = deserialize_values(val)
		self.assertEqual(9, len(val))
		self.assertEqual(data, deserialized)

	def test_serialize_decimal(self):
		data = [D('1.5'), D('2.5')]
		val = serialize_values(data)
		deserialized = deserialize_values(val)
		self.assertEqual(data, deserialized)
		self.assertEqual(10, len(val))

	def test_serialize_time(self):
		data = [time(1, 2, 3), time(23, 50, 40, 999999), time(23, 59, 59)]
		val = serialize_values(data)
		deserialized = deserialize_values(val)
		self.assertEqual(data, deserialized)
		self.assertEqual(14, len(val))

	def test_serialize_date(self):
		data = [date(2020, 1, 1), date(1960, 12, 31)]
		val = serialize_values(data)
		deserialized = deserialize_values(val)
		self.assertEqual(data, deserialized)
		self.assertEqual(10, len(val))

	def test_serialize_datetime(self):
		data = [
			datetime(2020, 1, 1, 1, 2, 3), # naive without microsecond
			datetime(1960, 12, 31, 23, 59, 59, tzinfo=timezone.utc), # localized without microsecond
			datetime(2020, 1, 1, 1, 2, 3, 999999), # naive with microsecond
			datetime(1960, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc), # localized with microsecond
		]
		val = serialize_values(data)
		deserialized = deserialize_values(val)
		self.assertEqual(data, deserialized)
		self.assertEqual(44, len(val))
