==================================================
Universal cursor and standard paginator for django
==================================================

|codecov| |version| |downloads| |license|

This package can render standard paginator and efficient cursor pagination.

Cursor pagination needs ordered queryset which can be used as unique key.

Install
-------

`pip install jango-universal-paginator`

Usage
-----

Settings
^^^^^^^^

.. code:: python

	INSTALLED_APPS = (
		# ...
		'django_universal_paginator',
	)

View
^^^^

.. code:: python

	# views.py

	class ObjectList(ListView):
		paginate_by = 10
		# model = ...

Template
^^^^^^^^

.. code:: html

	<!-- object_list.html -->
	{% load paginator_tags %}

	<ul>
		{% for object in object_list %}
			<li>{{ object }}</li>
		{% endfor %}
	</ul>

	<div class="pagination">{% pagination %}</div>

URLs
^^^^

.. code:: python

	# urls.py

	from django.urls import path, register_converter
	from django_universal_paginator.converter import PageConverter, CursorPageConverter

	register_converter(PageConverter, 'page')
	register_converter(CursorPageConverter, 'cursor_page')

	# standard
	url(r'^object-list/<page:page>', ObjectList.as_view(), name='object_list'),
	# or cursor
	url(r'^cursor/<cursor_page:page>', ObjectList.as_view(), name='cursor_list'),


Cursor pagination
^^^^^^^^^^^^^^^^^

To enable cursor paginator just extend ListView using
`django_universal_paginator.CursorPaginateView` and ensure, that queryset order_by
can be used to uniquely index object.

.. code:: python

	class List(CursorPaginateView, ListView):
		queryset = Book.objects.order_by('pk')

To use cursor pagination inside function based view, there is
`django_universal_paginator.paginate_cursor_queryset` shortcut.


Paginator template
^^^^^^^^^^^^^^^^^^

To override default paginator template create file `paginator/paginator.html` in
directory with templates. Example `paginator.html` file is located in
`sample_project/templates/paginator` directory.

.. |codecov| image:: https://codecov.io/gh/mireq/django-universal-paginator/branch/master/graph/badge.svg?token=QGY5B5X0F3
	:target: https://codecov.io/gh/mireq/django-universal-paginator

.. |version| image:: https://badge.fury.io/py/django-universal-paginator-generator.svg
	:target: https://pypi.python.org/pypi/django-universal-paginator-generator/

.. |downloads| image:: https://img.shields.io/pypi/dw/django-universal-paginator-generator.svg
	:target: https://pypi.python.org/pypi/django-universal-paginator-generator/

.. |license| image:: https://img.shields.io/pypi/l/django-universal-paginator-generator.svg
	:target: https://pypi.python.org/pypi/django-universal-paginator-generator/
