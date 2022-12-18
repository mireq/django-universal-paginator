# -*- coding: utf-8 -*-
from random import randint

from django.utils.crypto import get_random_string
from django.views.generic import TemplateView, ListView
from django_universal_paginator.cursor import CursorPaginateMixin

from .models import Random


LIST_DATA = []
for i in range(500):
	LIST_DATA.append(get_random_string(length=randint(1, 10)))


class SampleListView(ListView):
	paginate_by = 10

	def get_queryset(self):
		return LIST_DATA


class CursorListView(CursorPaginateMixin, SampleListView):
	def get_queryset(self):
		return Random.objects.order_by('pk')


home_view = TemplateView.as_view(template_name='home.html')
default_paginator_view = SampleListView.as_view(template_name='default.html')
large_paginator_view = SampleListView.as_view(template_name='large.html')
custom_template_paginator_view = SampleListView.as_view(template_name='custom_template.html')
cursor_list_view = CursorListView.as_view(template_name='large.html')
