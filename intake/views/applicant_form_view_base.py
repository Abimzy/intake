from django.views.generic.edit import FormView
from django.utils.translation import ugettext as _
from intake import models, utils, notifications
import intake.services.events_service as EventsService
import intake.services.messages_service as MessagesService
import logging
from django.shortcuts import redirect
from django.core.urlresolvers import reverse
from intake.exceptions import NoCountiesInSessionError
import intake.services.submissions as SubmissionsService
import intake.services.applicants as ApplicantsService
from project.jinja2 import oxford_comma


ERROR_MESSAGE = _(
    "There were some problems with your application. "
    "Please check the errors below.")

logger = logging.getLogger(__name__)


class ApplicantFormViewBase(FormView):
    session_key = 'form_in_progress'

    def check_for_session_based_redirects(self):
        if 'counties' not in self.session_data:
            error = NoCountiesInSessionError("No Counties in session data")
            logger.error(error)
            return redirect(reverse('intake-apply'))

    def dispatch(self, request, *args, **kwargs):
        self.session_data = utils.get_form_data_from_session(
            request, self.session_key)
        response = self.check_for_session_based_redirects()
        self.county_slugs = self.session_data.getlist('counties', [])
        self.counties = models.County.objects.filter(
            slug__in=self.county_slugs)
        self.formatted_county_names = [
            county.name + " County" for county in self.counties]
        if response:
            return response
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context.update(
            counties=self.counties, county_list=self.formatted_county_names)
        return context

    def form_valid(self, form):
        EventsService.log_form_page_complete(
            self.request, page_name=self.__class__.__name__)
        utils.save_form_data_to_session(
            self.request, self.session_key, form.data)
        return super().form_valid(form)

    def form_invalid(self, form):
        MessagesService.flash_errors(
            self.request, ERROR_MESSAGE, *form.non_field_errors())
        EventsService.log_form_validation_errors(
            self.request, errors=form.get_serialized_errors())
        return super().form_invalid(form)

    def get_receiving_organizations(self, form):
        if not getattr(self, 'receiving_organizations', None):
            self.receiving_organizations = [
                county.get_receiving_agency(form.cleaned_data)
                for county in self.counties]
        return self.receiving_organizations

    def finalize_application(self, form):
        organizations = self.get_receiving_organizations(form)
        applicant = \
            ApplicantsService.get_applicant_from_request_or_session(
                self.request)
        submission = SubmissionsService.create_submission(
            form, organizations, applicant.id)
        SubmissionsService.fill_pdfs_for_submission(
            submission, organizations=organizations)
        number = models.FormSubmission.objects.count()
        notifications.slack_new_submission.send(
            submission=submission, request=self.request,
            submission_count=number)
        sent_confirmations = \
            SubmissionsService.send_confirmation_notifications(submission)
        main_success_message = _(
            "You have applied for help in ") + oxford_comma(
                self.formatted_county_names)
        MessagesService.flash_success(
            self.request, main_success_message, *sent_confirmations)


def clear_form_session_data(request):
    utils.clear_session_data(
        request, ApplicantFormViewBase.session_key, 'applicant_id')
