# !/usr/bin/env python
# encoding: utf-8

from rest_framework import viewsets
from rest_framework.decorators import list_route

from seed.data_importer.meters_parser import MetersParser
from seed.data_importer.utils import (
    kbtu_thermal_conversion_factors,
    usage_point_id,
)
from seed.decorators import ajax_request_class
from seed.lib.mcm import reader
from seed.models import (
    Meter,
    ImportFile,
    PropertyView,
)
from seed.utils.meters import PropertyMeterReadingsExporter


class MeterViewSet(viewsets.ViewSet):

    @ajax_request_class
    @list_route(methods=['POST'])
    def parsed_meters_confirmation(self, request):
        body = dict(request.data)
        file_id = body['file_id']
        org_id = body['organization_id']

        import_file = ImportFile.objects.get(pk=file_id)
        parser = reader.MCMParser(import_file.local_file)
        raw_meter_data = list(parser.data)

        meters_parser = MetersParser(org_id, raw_meter_data)

        result = {}

        result["validated_type_units"] = meters_parser.validated_type_units()
        result["proposed_imports"] = meters_parser.proposed_imports()
        result["unlinkable_pm_ids"] = meters_parser.unlinkable_pm_ids

        return result

    @ajax_request_class
    @list_route(methods=['POST'])
    def greenbutton_parsed_meters_confirmation(self, request):
        body = dict(request.data)
        file_id = body['file_id']
        org_id = body['organization_id']
        view_id = body['view_id']

        import_file = ImportFile.objects.get(pk=file_id)
        parser = reader.GreenButtonParser(import_file.local_file)
        raw_meter_data = list(parser.data)

        property_id = PropertyView.objects.get(pk=view_id).property_id
        meters_parser = MetersParser(org_id, raw_meter_data, source_type=Meter.GREENBUTTON, property_id=property_id)

        result = {}

        result["validated_type_units"] = meters_parser.validated_type_units()
        result["proposed_imports"] = meters_parser.proposed_imports()

        import_file.matching_results_data['property_id'] = property_id
        import_file.save()

        return result

    @ajax_request_class
    @list_route(methods=['POST'])
    def property_meters(self, request):
        body = dict(request.data)
        property_view_id = body['property_view_id']

        property_id = PropertyView.objects.get(pk=property_view_id).property.id
        energy_types = dict(Meter.ENERGY_TYPES)

        return [
            {
                'id': meter.id,
                'type': energy_types[meter.type],
                'source': "PM" if meter.source == Meter.PORTFOLIO_MANAGER else "GB",
                'source_id': meter.source_id if meter.source == Meter.PORTFOLIO_MANAGER else usage_point_id(meter.source_id),
            }
            for meter
            in Meter.objects.filter(property_id=property_id)
        ]

    @ajax_request_class
    @list_route(methods=['POST'])
    def property_meter_usage(self, request):
        body = dict(request.data)
        property_view_id = body['property_view_id']
        org_id = body['organization_id']
        interval = body['interval']
        excluded_meter_ids = body['excluded_meter_ids']
        property_id = PropertyView.objects.get(pk=property_view_id).property.id

        exporter = PropertyMeterReadingsExporter(property_id, org_id, excluded_meter_ids)

        return exporter.readings_and_column_defs(interval)

    @ajax_request_class
    @list_route(methods=['GET'])
    def valid_types_units(self, request):
        return {
            type: list(units.keys())
            for type, units
            in kbtu_thermal_conversion_factors("US").items()
        }
