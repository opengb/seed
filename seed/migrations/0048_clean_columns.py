# -*- coding: utf-8 -*-
# Generated by Django 1.9.5 on 2017-01-19 21:18
from __future__ import unicode_literals

from django.db import migrations

from seed.models.columns import Column, ColumnMapping


# from seed.utils.generic import pp

def forwards(apps, schema_editor):
    for cm in ColumnMapping.objects.all():
        # pp(cm)
        # remove columns that are not used in any mappings

        # These two asserts should never get called!
        if cm.column_raw.count() > 1:
            assert ('more than one mapping')

        if cm.column_mapped.count() > 1:
            assert ('more than one mapping')

    # find which columns are not used in column mappings
    not_used_count = 0
    for c in Column.objects.all():
        cm_raw = ColumnMapping.objects.filter(column_raw=c)
        cm_mapped = ColumnMapping.objects.filter(column_mapped=c)

        if cm_raw.count() == 0 and cm_mapped.count() == 0:
            print "Column {}: {}.{} is not used in mappings".format(c.id, c.table_name,
                                                                    c.column_name)
            not_used_count += 1
            # c.delete()

    print "Total unused columns: {}".format(not_used_count)
    print "Total Columns: {}".format(Column.objects.all().count())

    # for cm in cms:
    #     print c.column_name
    #     pp(cm)
    # for c in Column.objects.all():
    # check if the table name is blank, if it is then
    # the extra_data field should be blank as well
    #
    # pp(c)

    exit()


class Migration(migrations.Migration):
    dependencies = [
        ('seed', '0047_auto_20170119_1318'),
    ]

    operations = [
        migrations.RunPython(forwards),
    ]
