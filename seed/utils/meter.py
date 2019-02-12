# !/usr/bin/env python
# encoding: utf-8

from calendar import monthrange

from config.settings.common import TIME_ZONE

from datetime import datetime

from django.utils.timezone import make_aware

from pytz import timezone

from seed.models import (
    Meter,
    PropertyState,
)


def parse_meter_details(meters_and_readings_details, property_link='Property Id', monthly=False):
    """
    Meter and meter reading details are parsed from meter usage data, converting
    that raw meter usage data into a format that is accepted by the two models.
    The goal of this method is to generate the following dictionary and return
    only its values:
    {
        <unique meter identifier>: {
            'property_id': <id>,
            'type': <char>,
            'units': <char>,
            ...(other meter metadata)
            'readings': [
                {
                    'start_time': <time>,
                    'end_time': <time>,
                    'reading': <float>
                },
                ...(more readings)
            ]
        },
        ...(more meters and their readings)
    }

    The unique identifier of a meter is composed of the values of it's details
    which include property_id, type, units, etc. This is used to easily associate
    readings to a previously parsed meter.
    """
    result = {}
    source_to_property_ids = {}  # tracked to reduce the number of database queries

    tz = timezone(TIME_ZONE)

    for details in meters_and_readings_details:
        meter_shared_details = {}

        source_id = details[property_link]

        meter_shared_details['source'] = 1  # probably need to be passed in as arg
        meter_shared_details['source_id'] = str(source_id)

        _get_property_id_from_source(source_id, meter_shared_details, source_to_property_ids)

        if monthly:
            start_time, end_time = _parse_times(details['Month'], tz)

        _parse_meter_readings(details, meter_shared_details, result, start_time, end_time)

    return list(result.values())


def _parse_times(month_year, tz):
    unaware_start = datetime.strptime(month_year, '%b-%y')
    start_time = make_aware(unaware_start, timezone=tz)

    days_in_month = monthrange(start_time.year, start_time.month)[1]
    unaware_end = datetime(start_time.year, start_time.month, days_in_month, 23, 59, 59)
    end_time = make_aware(unaware_end, timezone=tz)

    return start_time, end_time


def _get_property_id_from_source(source_id, shared_details, source_to_property_ids):
    """This is set up to avoid querying for the same property_id more than once"""
    property_id = source_to_property_ids.get(source_id, None)

    if property_id is not None:
        shared_details['property_id'] = property_id
    else:
        property_id = PropertyState.objects \
            .get(pm_property_id__exact=source_id) \
            .propertyview_set \
            .first() \
            .property_id

        shared_details['property_id'] = property_id
        source_to_property_ids[source_id] = property_id


def _parse_meter_readings(details, meter_shared_details, result, start_time, end_time):
    """
    Meter types (key/value pairs) of raw meter details are iterated over to
    generate individual meter readings. If a meter has not yet been parsed, it's
    first reading details are saved in a list. If a meter was previously parsed
    and has readings already, any new readings are appended to that list.
    """
    meter_types = [k for k, v in details.items() if ' Use  (' in k]

    for type in meter_types:
        meter_details = meter_shared_details.copy()

        meter_reading = {
            'start_time': start_time,
            'end_time': end_time,
            'reading': details[type]
        }

        _parse_type_and_units(type, meter_details)

        meter_identifier = '-'.join([str(v) for k, v in meter_details.items()])

        existing_property_meter = result.get(meter_identifier, None)

        if existing_property_meter is None:
            meter_details['readings'] = [meter_reading]

            result[meter_identifier] = meter_details
        else:
            existing_property_meter['readings'].append(meter_reading)


def _parse_type_and_units(type_unit, meter_details):
    type = type_unit[:(type_unit.find(" Use"))]
    meter_details['type'] = Meter.type_lookup[type]

    unit = type_unit[(type_unit.find('(') + 1):(type_unit.find(')'))]
    meter_details['units'] = Meter.unit_lookup[unit]
