# -*- coding: utf-8 -*-
# Generated by Django 1.9.13 on 2017-08-24 23:10
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('seed', '0074_columnmapping_units'),
    ]

    operations = [
        migrations.AddField(
            model_name='column',
            name='pint_unit',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]
