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
	Default template name for paginator, default: ``'paginator/paginator.html'``

Usage
-----

Template
^^^^^^^^

To use this library first add ``{% pagination %}`` to django template or
``{{ pagination() }}`` to jinja2 template.

.. code:: html

	<!-- object_list.html -->
	{% load paginator_tags %}

	<ul>
		{% for object in object_list %}
			<li>{{ object }}</li>
		{% endfor %}
	</ul>

	<div class="pagination">{% pagination %}</div>

To modify style look to
`paginator.html <https://github.com/mireq/django-universal-paginator/blob/master/django_universal_paginator/templates/paginator/paginator.html>`_.

URLs
^^^^

This package can be used without URL modification, but if you want clean URL
patterns without GET parameters, like ``/object-list/3/``, you can use following
code (example contains both methods - standard and cursor).

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


Classical navigation
^^^^^^^^^^^^^^^^^^^^

To use classical navigation, just add ``paginate_by`` attribute to class based
list view.


.. code:: python

	# views.py

	class ObjectList(ListView):
		paginate_by = 10
		# model = ...

If you are using function based views, you can use
``django_universal_paginator.utils.paginate_queryset``.

.. code:: python

	# views.py
	from django_universal_paginator.utils import paginate_queryset

	def list_view(request):
		queryset = Book.objects.order_by('pk')
		paginate_by = 10
		page = 1
		paginator, page, queryset, is_paginated = self.paginate_queryset(queryset, page,
		paginate_by)

		context = {
			"paginator": paginator,
			"page_obj": page,
			"is_paginated": is_paginated,
			"object_list": queryset,
		}

		reutrn render_to_string("list.html", context)


Cursor pagination
^^^^^^^^^^^^^^^^^

To use cursor pagination, queryset must be correctly ordered (order key must be
combination of keys which are unique across queryset).

.. code:: python

	# views.py
	from django.views.generic import ListView
	from django_universal_paginator.cursor import CursorPaginateMixin

	class List(CursorPaginateMixin, ListView):
		paginate_by = 10
		queryset = Book.objects.order_by('pk')


.. |codecov| image:: https://codecov.io/gh/mireq/django-universal-paginator/branch/master/graph/badge.svg?token=QGY5B5X0F3
	:target: https://codecov.io/gh/mireq/django-universal-paginator

.. |version| image:: https://badge.fury.io/py/django-universal-paginator.svg
	:target: https://pypi.python.org/pypi/django-universal-paginator/

.. |downloads| image:: https://img.shields.io/pypi/dw/django-universal-paginator.svg
	:target: https://pypi.python.org/pypi/django-universal-paginator/

.. |license| image:: https://img.shields.io/pypi/l/django-universal-paginator.svg
	:target: https://pypi.python.org/pypi/django-universal-paginator/
