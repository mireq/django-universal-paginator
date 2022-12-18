# -*- coding: utf-8 -*-
from django.urls import path, register_converter
from django_universal_paginator.converter import PageConverter, CursorPageConverter

from . import views


register_converter(PageConverter, 'page')
register_converter(CursorPageConverter, 'cursor_page')


urlpatterns = [
	path('', views.home_view, name='home'),
	path('default/<page:page>', views.default_paginator_view, name='default_paginator'),
	path('large/<page:page>', views.large_paginator_view, name='large_paginator'),
	path('custom-template/<page:page>', views.custom_template_paginator_view, name='custom_template_paginator'),
	path('cursor/<cursor_page:page>', views.cursor_list_view, name='cursor'),
]
