# -*- coding: utf-8 -*-
from django.db import models
from django.utils import timezone


class Book(models.Model):
	name = models.CharField(max_length=50)
	pages = models.IntegerField()
	is_published = models.BooleanField()
	pub_time = models.DateTimeField(default=timezone.now)
	rating = models.FloatField(blank=True, null=True)

	def __str__(self):
		return f'{self.name} ({self.pages} pages), published: {self.is_published}, rating: {self.rating}'


class Review(models.Model):
	book = models.ForeignKey(Book, on_delete=models.CASCADE)
	text = models.CharField(max_length=50)

	def __str__(self):
		return f'{self.text} ({self.book_id})'