# -*- coding: utf-8 -*-
# Generated by Django 1.9.13 on 2017-07-13 16:51
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('landing', '0007_seeduser_language_preference'),
    ]

    operations = [
        migrations.AddField(
            model_name='seeduser',
            name='prefers_metric',
            field=models.BooleanField(default=False),
        ),
    ]
