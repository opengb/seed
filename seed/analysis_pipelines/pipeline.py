import abc

from seed.lib.progress_data.progress_data import ProgressData
from seed.models import Analysis, AnalysisPropertyView, AnalysisMessage

from django.db import transaction
from celery import shared_task


@shared_task
def task_create_analysis_property_views(analysis_id, property_view_ids, progress_data_key=None):
    """A celery task which batch creates the AnalysisPropertyViews for the analysis.
    It will create AnalysisMessages for any property view IDs that couldn't be
    used to create an AnalysisPropertyView.

    :param analysis_id: int
    :param property_view_ids: list[int]
    :param progress_data_key: str, optional
    :returns: list[int], IDs of the successfully created AnalysisPropertyViews
    """
    if progress_data_key is not None:
        progress_data = ProgressData.from_key(progress_data_key)
        progress_data.step('Copying property data')
    analysis_view_ids, failures = AnalysisPropertyView.batch_create(analysis_id, property_view_ids)
    for failure in failures:
        AnalysisMessage.objects.create(
            analysis_id=analysis_id,
            type=AnalysisMessage.DEFAULT,
            user_message=f'Failed to copy property data for PropertyView ID {failure.property_view_id}: {failure.message}',
        )
    return analysis_view_ids


class AnalysisPipelineException(Exception):
    pass


class AnalysisPipeline(abc.ABC):
    """
    AnalysisPipeline is an abstract class for defining workflows for preparing,
    running, and post processing analyses.
    """
    def __init__(self, analysis_id):
        self._analysis_id = analysis_id

    def prepare_analysis(self, property_view_ids):
        """Entrypoint for preparing an analysis.

        :param property_view_ids: list[int]
        :returns: str, A ProgressData key
        """
        with transaction.atomic():
            locked_analysis = Analysis.objects.select_for_update().get(id=self._analysis_id)
            if locked_analysis.status is Analysis.PENDING_CREATION:
                locked_analysis.status = Analysis.CREATING
                locked_analysis.save()
            else:
                raise AnalysisPipelineException('Analysis has already been prepared or is currently being prepared')

        return self._prepare_analysis(self._analysis_id, property_view_ids)

    def start_analysis(self):
        """Entrypoint for starting an analysis.

        :returns: str, A ProgressData key
        """
        with transaction.atomic():
            locked_analysis = Analysis.objects.select_for_update().get(id=self._analysis_id)
            if locked_analysis.status is Analysis.READY:
                locked_analysis.status = Analysis.QUEUED
                locked_analysis.save()
            else:
                raise AnalysisPipelineException('Analysis cannot be started')

        return self._start_analysis()

    def fail(self, message, progress_data_key=None):
        """Fails the analysis.

        :param message: str, message to create an AnalysisMessage with
        :param progress_data_key: str, fails the progress data if this key is provided
        """
        with transaction.atomic():
            locked_analysis = Analysis.objects.select_for_update().get(id=self._analysis_id)

            if progress_data_key is not None:
                progress_data = ProgressData.from_key(progress_data_key)
                progress_data.finish_with_error(message)

            if locked_analysis.in_terminal_state():
                raise AnalysisPipelineException(f'Analysis is already in a terminal state: status {locked_analysis.status}')

            locked_analysis.status = Analysis.FAILED
            locked_analysis.save()

            AnalysisMessage.objects.create(
                analysis_id=self._analysis_id,
                type=AnalysisMessage.DEFAULT,
                user_message=message,
            )

    @abc.abstractmethod
    def _prepare_analysis(self, analysis_id, property_view_ids):
        """Abstract method which should do the work necessary for preparing
        an analysis, e.g. creating input file(s)

        :param analysis_id: int
        :param property_view_ids: list[int]
        :returns: str, A ProgressData key
        """
        pass

    @abc.abstractmethod
    def _start_analysis(self):
        """Abstract method which should start the analysis, e.g. make HTTP requests
        to the analysis service.

        :param analysis_id: int
        :returns: str, A ProgressData key
        """
        pass
