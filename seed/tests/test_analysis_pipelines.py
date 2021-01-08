# !/usr/bin/env python
# encoding: utf-8
"""
:copyright (c) 2014 - 2020, The Regents of the University of California, through Lawrence Berkeley National Laboratory (subject to receipt of any required approvals from the U.S. Department of Energy) and contributors. All rights reserved.  # NOQA
:author
"""
from datetime import datetime
from io import BytesIO
import json
from os import path
from unittest.mock import patch

from lxml import etree

from pytz import timezone

from requests import Response

from django.db.models import Q
from django.test import TestCase, override_settings
from django.utils.timezone import make_aware

from config.settings.common import TIME_ZONE, BASE_DIR

from seed.landing.models import SEEDUser as User
from seed.models import (
    Meter,
    MeterReading,
    Analysis,
    PropertyState,
    AnalysisInputFile,
    AnalysisMessage,
    AnalysisPropertyView,
)
from seed.test_helpers.fake import (
    FakeAnalysisFactory,
    FakeAnalysisPropertyViewFactory,
    FakePropertyStateFactory,
    FakePropertyViewFactory,
)
from seed.utils.organizations import create_organization
from seed.analysis_pipelines.pipeline import (
    AnalysisPipelineException,
    AnalysisPipeline,
    task_create_analysis_property_views,
    check_analysis_status
)
from seed.analysis_pipelines.bsyncr import _build_bsyncr_input, BsyncrPipeline, _parse_analysis_property_view_id, PREMISES_ID_NAME
from seed.building_sync.building_sync import BuildingSync
from seed.building_sync.mappings import NAMESPACES


class MockPipeline(AnalysisPipeline):

    def _prepare_analysis(self, analysis_id, property_view_ids):
        analysis = Analysis.objects.get(id=analysis_id)
        analysis.status = Analysis.READY
        analysis.save()

    def _start_analysis(self):
        analysis = Analysis.objects.get(id=self._analysis_id)
        analysis.status = Analysis.RUNNING
        analysis.save()


class TestAnalysisPipeline(TestCase):
    def setUp(self):
        user_details = {
            'username': 'test_user@demo.com',
            'password': 'test_pass',
            'email': 'test_user@demo.com',
            'first_name': 'Test',
            'last_name': 'User',
        }
        self.user = User.objects.create_user(**user_details)
        self.org, _, _ = create_organization(self.user)
        self.analysis = (
            FakeAnalysisFactory(organization=self.org, user=self.user)
            .get_analysis()
        )

    def test_prepare_analysis_raises_exception_when_analysis_status_indicates_already_prepared(self):
        # Setup
        # set status as already running, which should prevent the analysis from
        # starting preparation (this could be any status that's not PENDING_CREATION)
        self.analysis.status = Analysis.RUNNING
        self.analysis.save()
        pipeline = MockPipeline(self.analysis.id)

        # Act / Assert
        # shouldn't matter what values are passed for property_view_ids
        with self.assertRaises(AnalysisPipelineException) as context:
            pipeline.prepare_analysis([1, 2, 3])

        self.assertTrue('Analysis has already been prepared or is currently being prepared' in str(context.exception))

        # the status should not have changed
        self.analysis.refresh_from_db()
        self.assertTrue(Analysis.RUNNING, self.analysis.status)

    def test_prepare_analysis_is_successful_when_analysis_status_is_valid(self):
        # Setup
        self.assertEqual(self.analysis.status, Analysis.PENDING_CREATION)
        pipeline = MockPipeline(self.analysis.id)

        # Act
        # shouldn't matter what values are passed for property_view_ids
        # The MockPipeline should just set the status to READY
        pipeline.prepare_analysis([1, 2, 3])

        # Assert
        self.analysis.refresh_from_db()
        self.assertEqual(Analysis.READY, self.analysis.status)

    def test_start_analysis_is_successful_when_analysis_status_is_ready(self):
        # Setup
        self.analysis.status = Analysis.READY
        self.analysis.save()
        pipeline = MockPipeline(self.analysis.id)

        # Act
        pipeline.start_analysis()

        # Assert
        self.analysis.refresh_from_db()
        self.assertEqual(Analysis.RUNNING, self.analysis.status)

    def test_start_analysis_raises_exception_when_analysis_status_isnt_ready(self):
        # Setup
        self.analysis.status = Analysis.CREATING
        self.analysis.save()
        pipeline = MockPipeline(self.analysis.id)

        # Act
        with self.assertRaises(AnalysisPipelineException) as context:
            pipeline.start_analysis()

        # Assert
        self.assertTrue('Analysis cannot be started' in str(context.exception))
        # the status should not have changed
        self.analysis.refresh_from_db()
        self.assertEqual(Analysis.CREATING, self.analysis.status)

    def test_fail_sets_status_to_failed_when_not_already_in_terminal_state(self):
        # Setup
        pipeline = MockPipeline(self.analysis.id)
        failure_message = 'Bad'

        # Act
        pipeline.fail(failure_message)

        # Assert
        self.analysis.refresh_from_db()
        self.assertEqual(Analysis.FAILED, self.analysis.status)
        # a message linked to the analysis should have been created as well
        message = AnalysisMessage.objects.get(analysis=self.analysis)
        self.assertTrue(failure_message in message.user_message)

    def test_fail_raises_exception_when_analysis_is_already_in_terminal_state(self):
        # Setup
        self.analysis.status = Analysis.COMPLETED
        self.analysis.save()
        pipeline = MockPipeline(self.analysis.id)

        # Act
        with self.assertRaises(AnalysisPipelineException) as context:
            pipeline.fail('Double plus ungood')

        # Assert
        self.assertTrue('Analysis is already in a terminal state' in str(context.exception))
        # the status should not have changed
        self.analysis.refresh_from_db()
        self.assertEqual(Analysis.COMPLETED, self.analysis.status)

    def test_stop_sets_status_to_stopped_when_not_in_terminal_state(self):
        # Setup
        self.analysis.status = Analysis.RUNNING
        self.analysis.save()
        pipeline = MockPipeline(self.analysis.id)

        # Act
        pipeline.stop()

        # Assert
        self.analysis.refresh_from_db()
        self.assertEqual(Analysis.STOPPED, self.analysis.status)

    def test_stop_does_not_change_status_if_already_in_terminal_state(self):
        # Setup
        self.analysis.status = Analysis.FAILED
        self.analysis.save()
        pipeline = MockPipeline(self.analysis.id)

        # Act
        pipeline.stop()

        # Assert
        self.analysis.refresh_from_db()
        self.assertEqual(Analysis.FAILED, self.analysis.status)

    def test_task_create_analysis_property_views_creates_messages_for_failed_property_views(self):
        # Setup
        property_view = (
            FakePropertyViewFactory(organization=self.org, user=self.user)
            .get_property_view()
        )
        bogus_property_view_id = -1
        property_view_ids = [bogus_property_view_id, property_view.id]

        # Act
        task_create_analysis_property_views(self.analysis.id, property_view_ids)

        # Assert
        # a message for the bad property view should have been created
        message = AnalysisMessage.objects.get(analysis=self.analysis)
        self.assertTrue(f'Failed to copy property data for PropertyView ID {bogus_property_view_id}' in message.user_message)

    def test_check_analysis_status_calls_decorated_function_when_status_is_as_expected(self):
        # Setup
        @check_analysis_status(Analysis.RUNNING)
        def my_func(analysis_id):
            return 'I did work'

        self.analysis.status = Analysis.RUNNING
        self.analysis.save()

        # Act
        res = my_func(self.analysis.id)

        # Assert
        self.assertEqual('I did work', res)

    def test_check_analysis_status_works_when_decorated_func_called_with_kwargs(self):
        # Setup
        @check_analysis_status(Analysis.RUNNING)
        def my_func(analysis_id):
            return 'I did work'

        self.analysis.status = Analysis.RUNNING
        self.analysis.save()

        # Act
        res = my_func(analysis_id=self.analysis.id)

        # Assert
        self.assertEqual('I did work', res)

    def test_check_analysis_status_works_when_decorated_func_has_multiple_args(self):
        # Setup
        @check_analysis_status(Analysis.RUNNING)
        def my_func(my_param_1, my_param_2, analysis_id, my_param_3):
            return 'I did work'

        self.analysis.status = Analysis.RUNNING
        self.analysis.save()

        # Act
        res = my_func(-1, -1, self.analysis.id, -1)

        # Assert
        self.assertEqual('I did work', res)

    def test_check_analysis_status_raises_exception_when_analysis_status_is_not_as_expected(self):
        # Setup
        expected_status = Analysis.RUNNING

        @check_analysis_status(expected_status)
        def my_func(analysis_id):
            return 'I did work'

        # set status to something unexpected
        self.analysis.status = Analysis.STOPPED
        self.analysis.save()

        # Act/Assert
        with self.assertRaises(AnalysisPipelineException) as context:
            my_func(self.analysis.id)

        self.assertIn(f'Expected analysis status to be {expected_status}', str(context.exception))


# override the BSYNCR_SERVER_HOST b/c otherwise the pipeline will not run (doesn't have to be valid b/c we mock requests)
@override_settings(BSYNCR_SERVER_HOST='bogus.host.com')
class TestBsyncrPipeline(TestCase):
    def setUp(self):
        user_details = {
            'username': 'test_user@demo.com',
            'password': 'test_pass',
            'email': 'test_user@demo.com',
            'first_name': 'Test',
            'last_name': 'User',
        }
        self.user = User.objects.create_user(**user_details)
        self.org, _, _ = create_organization(self.user)

        property_state = (
            FakePropertyStateFactory(organization=self.org).get_property_state(
                # fields required for analysis
                latitude=39.76550841416409,
                longitude=-104.97855661401148
            )
        )
        self.analysis_property_view = (
            FakeAnalysisPropertyViewFactory(organization=self.org, user=self.user).get_analysis_property_view(
                property_state=property_state,
                # analysis args
                name='Quite neat',
                service=Analysis.BSYNCR,
            )
        )

        self.meter = Meter.objects.create(
            property=self.analysis_property_view.property,
            source=Meter.PORTFOLIO_MANAGER,
            source_id="Source ID",
            type=Meter.ELECTRICITY_GRID,
        )
        tz_obj = timezone(TIME_ZONE)
        self.meter_reading = MeterReading.objects.create(
            meter=self.meter,
            start_time=make_aware(datetime(2018, 1, 1, 0, 0, 0), timezone=tz_obj),
            end_time=make_aware(datetime(2018, 1, 2, 0, 0, 0), timezone=tz_obj),
            reading=12345,
            source_unit='kWh',
            conversion_factor=1.00
        )

        #
        # Setup more properties with linked meters with 12 valid meter readings.
        # These properties, unmodified, should successfully run thorugh the bsyncr pipeline
        #
        property_view_factory = FakePropertyViewFactory(organization=self.org)
        self.good_property_views = []
        self.num_good_property_views = 3
        for i in range(self.num_good_property_views):
            pv = property_view_factory.get_property_view(
                # fields required for analysis
                latitude=39.76550841416409,
                longitude=-104.97855661401148
            )
            # TODO: remove these lines saving the state once fixed, see issue #2493
            PropertyState.objects.get(id=pv.state.id).save()
            pv.refresh_from_db()
            self.good_property_views.append(pv)

        self.analysis_b = (
            FakeAnalysisFactory(organization=self.org, user=self.user)
            .get_analysis(
                name='Good Analysis',
                service=Analysis.BSYNCR
            )
        )

        self.good_meters = []
        for i in range(self.num_good_property_views):
            self.good_meters.append(
                Meter.objects.create(
                    property=self.good_property_views[i].property,
                    source=Meter.PORTFOLIO_MANAGER,
                    source_id="Source ID",
                    type=Meter.ELECTRICITY_GRID,
                )
            )
            tz_obj = timezone(TIME_ZONE)
            for j in range(1, 13):
                MeterReading.objects.create(
                    meter=self.good_meters[i],
                    start_time=make_aware(datetime(2019, j, 1, 0, 0, 0), timezone=tz_obj),
                    end_time=make_aware(datetime(2019, j, 28, 0, 0, 0), timezone=tz_obj),
                    reading=12345,
                    source_unit='kWh',
                    conversion_factor=1.00
                )

    def _mock_bsyncr_service_request_factory(self, error_messages=None):
        """Factory for returning a patched _bsyncr_service_request.
        If error_messages is None, it will construct a bsyncr output file for the
        response.

        :param error_messages: list[str], list of error messages to return in response
        """
        def _build_bsyncr_output(file_):
            # copy the example bsyncr output file then update the ID within it
            bsyncr_output_example_file = path.join(BASE_DIR, 'seed', 'tests', 'data', 'example-bsyncr-output.xml')
            bsyncr_output_tree = etree.parse(bsyncr_output_example_file)
            id_value_elem = bsyncr_output_tree.xpath(
                f'//auc:PremisesIdentifier[auc:IdentifierCustomName = "{PREMISES_ID_NAME}"]/auc:IdentifierValue',
                namespaces=NAMESPACES
            )
            analysis_property_view_id = _parse_analysis_property_view_id(file_.path)
            id_value_elem[0].text = str(analysis_property_view_id)
            return etree.tostring(bsyncr_output_tree, pretty_print=True)

        def _mock_request(file_):
            # mock the call to _bsyncr_service_request by returning a constructed Response
            the_response = Response()
            if error_messages is not None:
                the_response.status_code = 400
                body_dict = {
                    'errors': [{'detail': msg, 'code': '400'} for msg in error_messages]
                }
                the_response._content = json.dumps(body_dict).encode()
            else:
                the_response.status_code = 200
                the_response._content = _build_bsyncr_output(file_)

            return the_response

        return _mock_request

    def test_build_bsyncr_input_returns_valid_bsync_document(self):
        # Act
        doc, errors = _build_bsyncr_input(self.analysis_property_view, self.meter)
        tree = etree.parse(BytesIO(doc))

        # Assert
        self.assertEqual(0, len(errors))

        ts_elems = tree.xpath('//auc:TimeSeries', namespaces=NAMESPACES)
        self.assertEqual(self.meter.meter_readings.count(), len(ts_elems))

        # throws exception if document is not valid
        schema = BuildingSync.get_schema(BuildingSync.BUILDINGSYNC_V2_2_0)
        schema.validate(tree)

    def test_build_bsyncr_input_returns_errors_if_state_missing_info(self):
        # Setup
        # remove some required fields
        property_state = self.analysis_property_view.property_state
        property_state.latitude = None
        property_state.longitude = None
        property_state.save()

        # Act
        doc, errors = _build_bsyncr_input(self.analysis_property_view, self.meter)

        # Assert
        self.assertIsNone(doc)
        self.assertEqual(2, len(errors))
        self.assertTrue('Linked PropertyState is missing longitude' in errors)
        self.assertTrue('Linked PropertyState is missing latitude' in errors)

    def test_build_bsyncr_input_returns_error_if_reading_missing_value(self):
        # Setup
        # remove some required fields
        self.meter_reading.reading = None
        self.meter_reading.save()

        # Act
        doc, errors = _build_bsyncr_input(self.analysis_property_view, self.meter)

        # Assert
        self.assertIsNone(doc)
        self.assertEqual(1, len(errors))
        self.assertTrue('has no reading value' in errors[0])

    def test_prepare_analysis_is_successful_when_properly_setup(self):
        # Act
        pipeline = BsyncrPipeline(self.analysis_b.id)
        pipeline.prepare_analysis([pv.id for pv in self.good_property_views])

        # Assert
        self.analysis_b.refresh_from_db()
        self.assertEqual(Analysis.READY, self.analysis_b.status)

        # check an input file was created for each property
        input_files = AnalysisInputFile.objects.filter(analysis=self.analysis_b)
        self.assertEqual(len(self.good_property_views), input_files.count())

        # verify there were no messages
        messages = AnalysisMessage.objects.filter(
            Q(analysis=self.analysis_b) | Q(analysis_property_view__analysis_id=self.analysis_b)
        )
        self.assertEqual(0, messages.count())

    def test_prepare_analysis_creates_message_for_view_when_no_meter(self):
        # Setup
        # unlink a meter from its property to make the property view Bad
        target_meter = self.good_meters[0]
        original_meter_property_id = target_meter.property.id
        target_meter.property = None
        target_meter.save()

        # Act
        pipeline = BsyncrPipeline(self.analysis_b.id)
        pipeline.prepare_analysis([pv.id for pv in self.good_property_views])

        # Assert
        self.analysis_b.refresh_from_db()
        self.assertEqual(Analysis.READY, self.analysis_b.status)

        # verify a message was linked to the Bad analysis property view
        analysis_property_view = AnalysisPropertyView.objects.get(
            analysis=self.analysis_b,
            property=original_meter_property_id,
        )
        messages = AnalysisMessage.objects.filter(analysis_property_view=analysis_property_view)
        self.assertEqual(1, messages.count())
        self.assertTrue('Property has no linked electricity meters with 12 or more readings' in messages[0].user_message)

    def test_prepare_analysis_fails_when_it_fails_to_make_at_least_one_input_file(self):
        # Setup
        # unlink _all_ meters to the properties, making them all Bad
        for meter in self.good_meters:
            meter.property = None
            meter.save()

        # Act
        pipeline = BsyncrPipeline(self.analysis_b.id)
        property_view_ids = [pv.id for pv in self.good_property_views]

        # it should raise an exception b/c no input files were created
        with self.assertRaises(AnalysisPipelineException):
            pipeline.prepare_analysis(property_view_ids)

        # Assert
        self.analysis_b.refresh_from_db()
        self.assertEqual(Analysis.FAILED, self.analysis_b.status)

        # there should be a message for every property, saying it's Bad
        analysis_property_view_ids = AnalysisPropertyView.objects.filter(
            analysis=self.analysis_b,
        ).values_list('id', flat=True)
        messages = AnalysisMessage.objects.filter(
            analysis_property_view_id__in=analysis_property_view_ids
        )
        self.assertEqual(len(self.good_property_views), messages.count())

        # there should also be a message at analysis level saying things are Bad
        # because no input files were created
        analysis_message = AnalysisMessage.objects.get(
            analysis=self.analysis_b,
            analysis_property_view=None,
        )
        self.assertTrue('No files were able to be prepared for the analysis', analysis_message.user_message)

    def test_start_analysis_is_successful_when_inputs_are_valid(self):
        # Setup
        # prepare the analysis
        pipeline = BsyncrPipeline(self.analysis_b.id)
        property_view_ids = [pv.id for pv in self.good_property_views]
        pipeline.prepare_analysis(property_view_ids)

        self.analysis_b.refresh_from_db()
        self.assertEqual(Analysis.READY, self.analysis_b.status)

        # Act
        mock_bsyncr_service_request = self._mock_bsyncr_service_request_factory(error_messages=None)
        with patch('seed.analysis_pipelines.bsyncr._bsyncr_service_request', side_effect=mock_bsyncr_service_request):
            pipeline.start_analysis()

        # Assert
        self.analysis_b.refresh_from_db()
        self.assertEqual(Analysis.COMPLETED, self.analysis_b.status)

        # there should be no messages
        analysis_messages = AnalysisMessage.objects.filter(analysis=self.analysis_b)
        self.assertEqual(0, analysis_messages.count())

        # each property view should have parsed results stored
        # NOTE: these results won't change because they come from the example bsyncr output file
        expected_parsed_results = {
            'models': [
                {
                    "EndTimestamp": "2013-02-13T00:00:00",
                    "StartTimestamp": "2012-03-13T00:00:00",
                    "DerivedModelInputs": {
                        "ResponseVariable": {
                            "ResponseVariableName": "Electricity",
                            "ResponseVariableUnits": "kWh",
                            "ResponseVariableEndUse": "All end uses",
                        },
                        "IntervalFrequency": "Month",
                        "ExplanatoryVariables": {
                            "ExplanatoryVariable": {
                                "ExplanatoryVariableName": "Drybulb Temperature",
                                "ExplanatoryVariableUnits": "Fahrenheit, F",
                            }
                        },
                    },
                    "DerivedModelPerformance": {
                        "NDBE": "0.00",
                        "NMBE": "0.00",
                        "CVRMSE": "54.48",
                        "RSquared": "0.2",
                    },
                    "DerivedModelCoefficients": {
                        "Guideline14Model": {
                            "Beta1": "0.0730836792337458",
                            "Intercept": "2.62426286471561",
                            "ModelType": "2 parameter simple linear regression",
                        }
                    },
                }
            ]
        }
        analysis_property_views = AnalysisPropertyView.objects.filter(analysis=self.analysis_b)
        for analysis_property_view in analysis_property_views:
            self.assertDictEqual(expected_parsed_results, analysis_property_view.parsed_results)

    def test_start_analysis_fails_when_bsyncr_returns_errors(self):
        # Setup
        # prepare the analysis
        pipeline = BsyncrPipeline(self.analysis_b.id)
        property_view_ids = [pv.id for pv in self.good_property_views]
        pipeline.prepare_analysis(property_view_ids)

        self.analysis_b.refresh_from_db()
        self.assertEqual(Analysis.READY, self.analysis_b.status)

        # Act
        mock_bsyncr_service_request = self._mock_bsyncr_service_request_factory(error_messages=['Something is Bad'])
        with self.assertRaises(AnalysisPipelineException) as context:
            with patch('seed.analysis_pipelines.bsyncr._bsyncr_service_request', side_effect=mock_bsyncr_service_request):
                pipeline.start_analysis()

        # Assert
        self.assertTrue('Failed to get results for all properties' in str(context.exception))
        self.analysis_b.refresh_from_db()
        self.assertEqual(Analysis.FAILED, self.analysis_b.status)

        # there should be a generic analysis message indicating all properties failed
        analysis_generic_message = AnalysisMessage.objects.get(analysis=self.analysis_b, analysis_property_view__isnull=True)
        self.assertEqual('Failed to get results for all properties', analysis_generic_message.user_message)

        # every property should have a linked message with the bsyncr error
        analysis_messages = AnalysisMessage.objects.filter(analysis=self.analysis_b, analysis_property_view__isnull=False)
        self.assertEqual(len(property_view_ids), analysis_messages.count())
        for analysis_message in analysis_messages:
            self.assertTrue('Unexpected error from bsyncr service' in analysis_message.user_message)
