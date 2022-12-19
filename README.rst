========================================
Cursor and standard paginator for django
========================================

|codecov| |version| |downloads| |license|

This package is used to create standard or cursor navigation for django.

It has builtin templates, so you can use this library with minimal effort.
Library can be used with `jinja2` templates. If you are using ``django_jinja``
package, additional template tags are automatically registered to `jinja2`
engine.

If you are using cursor pagination, the queryset must be ordered with
combination of data fields, which are unique across query.

Cursor pagination supports checking for next / previous page presence without
any additional queries. There is used only single query to select records, no
additional queries to `count` checking or next / previous checking.

Install
-------

.. code:: bash

	pip install django-universal-paginator

To ``INSTALLED_APPS`` add ``django_universal_paginator``.

.. code:: python

	INSTALLED_APPS = (
		# ...
		'django_universal_paginator',
	)

Settings
--------

Classical paginator support following settings:

``PAGINATOR_ON_EACH_SIDE``
	Count of links around current page, default: 3
``PAGINATOR_ON_ENDS``
	Link count on start / end of list, default: 1
``PAGINATOR_TEMPLATE_NAME``
	Default template name for paginator, default ``'paginator/paginator.html'``





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

.. |version| image:: https://badge.fury.io/py/django-universal-paginator.svg
	:target: https://pypi.python.org/pypi/django-universal-paginator/

.. |downloads| image:: https://img.shields.io/pypi/dw/django-universal-paginator.svg
	:target: https://pypi.python.org/pypi/django-universal-paginator/

.. |license| image:: https://img.shields.io/pypi/l/django-universal-paginator.svg
	:target: https://pypi.python.org/pypi/django-universal-paginator/
