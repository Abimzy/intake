
from unittest import skipUnless
from unittest.mock import patch
from django.core.urlresolvers import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from intake.tests import mock
from intake.tests.base_testcases import IntakeDataTestCase, DELUXE_TEST
from intake import models, constants
from intake.views import application_form_views
from formation import fields

from project.jinja2 import url_with_ids


class TestViews(IntakeDataTestCase):

    fixtures = [
        'counties',
        'organizations',
        'mock_profiles',
        'mock_2_submissions_to_sf_pubdef']

    def set_session_counties(self, counties=None):
        if not counties:
            counties = [constants.Counties.SAN_FRANCISCO]
        self.set_session(form_in_progress={
            'counties': counties})

    def test_home_view(self):
        response = self.client.get(reverse('intake-home'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Clear My Record', response.content.decode('utf-8'))

    def test_apply_view(self):
        self.set_session_counties()
        response = self.client.get(reverse('intake-county_application'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Apply to Clear My Record',
                      response.content.decode('utf-8'))
        self.assertNotContains(response, "This field is required.")
        self.assertNotContains(response, "warninglist")

    def test_confirm_view(self):
        self.be_anonymous()
        base_data = dict(
            counties=['sanfrancisco'],
            **mock.NEW_RAW_FORM_DATA)
        self.set_session(
            form_in_progress=base_data)
        response = self.client.get(reverse('intake-confirm'))
        self.assertContains(response, base_data['first_name'][0])
        self.assertContains(response, base_data['last_name'][0])
        self.assertContains(
            response,
            fields.AddressField.is_recommended_error_message)
        self.assertContains(
            response,
            fields.SocialSecurityNumberField.is_recommended_error_message)
        self.assertContains(
            response,
            fields.DateOfBirthField.is_recommended_error_message)

    @patch('intake.models.get_parser')
    @patch(
        'intake.views.application_form_views.models.FormSubmission'
        '.send_confirmation_notifications')
    @patch(
        'intake.views.session_view_base.notifications'
        '.slack_new_submission.send')
    def test_anonymous_user_can_fill_out_app_and_reach_thanks_page(
            self, slack, send_confirmation, get_parser):
        get_parser.return_value.fill_pdf.return_value = b'a pdf'
        self.be_anonymous()
        result = self.client.fill_form(
            reverse('intake-apply'),
            counties=['sanfrancisco']
        )
        self.assertRedirects(result, reverse('intake-county_application'))
        result = self.client.fill_form(
            reverse('intake-county_application'),
            first_name="Anonymous",
            last_name="Anderson",
            ssn='123091203',
            **{
                'dob.day': '10',
                'dob.month': '10',
                'dob.year': '80',
                'address.street': '100 Market St',
                'address.city': 'San Francisco',
                'address.state': 'CA',
                'address.zip': '99999',
            })
        self.assertRedirects(result, reverse('intake-thanks'))
        thanks_page = self.client.get(result.url)
        filled_pdf = models.FilledPDF.objects.first()
        self.assertTrue(filled_pdf)
        self.assertTrue(filled_pdf.pdf)
        self.assertNotEqual(filled_pdf.pdf.size, 0)
        submission = models.FormSubmission.objects.order_by('-pk').first()
        self.assertEqual(filled_pdf.submission, submission)
        organization = submission.organizations.first()
        self.assertEqual(filled_pdf.original_pdf, organization.pdfs.first())
        self.assertContains(thanks_page, "Thank")
        self.assert_called_once_with_types(
            slack,
            submission='FormSubmission',
            request='WSGIRequest',
            submission_count='int')
        send_confirmation.assert_called_once_with()

    @patch('intake.models.get_parser')
    @patch(
        'intake.views.application_form_views.models.FormSubmission'
        '.send_confirmation_notifications')
    @patch(
        'intake.views.session_view_base.notifications'
        '.slack_new_submission.send')
    def test_apply_with_name_only(self, slack, send_confirmation, get_parser):
        get_parser.return_value.fill_pdf.return_value = b'a pdf'
        self.be_anonymous()
        result = self.client.fill_form(
            reverse('intake-apply'),
            counties=['sanfrancisco'],
            follow=True
        )
        # this should raise warnings
        result = self.client.fill_form(
            reverse('intake-county_application'),
            first_name="Foo",
            last_name="Bar"
        )
        self.assertRedirects(
            result, reverse('intake-confirm'), fetch_redirect_response=False)
        result = self.client.get(result.url)
        self.assertContains(result, "Foo")
        self.assertContains(result, "Bar")
        self.assertContains(
            result, fields.AddressField.is_recommended_error_message)
        self.assertContains(
            result,
            fields.SocialSecurityNumberField.is_recommended_error_message)
        self.assertContains(
            result, fields.DateOfBirthField.is_recommended_error_message)
        self.assertContains(
            result, application_form_views.Confirm.incoming_message)
        slack.assert_not_called()
        result = self.client.fill_form(
            reverse('intake-confirm'),
            first_name="Foo",
            last_name="Bar",
            follow=True
        )
        self.assertEqual(result.wsgi_request.path, reverse('intake-thanks'))
        self.assert_called_once_with_types(
            slack,
            submission='FormSubmission',
            request='WSGIRequest',
            submission_count='int')
        send_confirmation.assert_called_once_with()

    @skipUnless(DELUXE_TEST, "Super slow, set `DELUXE_TEST=1` to run")
    @patch('intake.notifications.slack_submissions_viewed.send')
    def test_authenticated_user_can_see_filled_pdf(self, slack):
        self.be_sfpubdef_user()
        submission = self.sf_pubdef_submissions[0]
        filled_pdf_bytes = self.fillable.fill(submission)
        pdf_file = SimpleUploadedFile('filled.pdf', filled_pdf_bytes,
                                      content_type='application/pdf')
        filled_pdf_model = models.FilledPDF(
            original_pdf=self.fillable,
            submission=submission,
            pdf=pdf_file
        )
        filled_pdf_model.save()
        pdf = self.client.get(reverse('intake-filled_pdf',
                                      kwargs=dict(
                                          submission_id=submission.id
                                      )))
        self.assertTrue(len(pdf.content) > 69000)
        self.assertEqual(type(pdf.content), bytes)

    @skipUnless(DELUXE_TEST, "Super slow, set `DELUXE_TEST=1` to run")
    @patch('intake.notifications.slack_submissions_viewed.send')
    @patch('intake.notifications.slack_simple.send')
    def test_authenticated_user_can_get_filled_pdf_without_building(
            self, slack_simple, slack_viewed):
        """
        test_authenticated_user_can_get_filled_pdf_without_building

        this tests that a pdf will be served even if not pregenerated
        """
        self.be_sfpubdef_user()
        submission = self.sf_pubdef_submissions[0]
        pdf = self.client.get(reverse('intake-filled_pdf',
                                      kwargs=dict(
                                          submission_id=submission.id
                                      )))
        self.assertTrue(len(pdf.content) > 69000)
        self.assertEqual(type(pdf.content), bytes)

    def test_authenticated_user_can_see_list_of_submitted_apps(self):
        self.be_cfa_user()
        index = self.client.get(reverse('intake-app_index'))
        for submission in models.FormSubmission.objects.all():
            self.assertContains(
                index,
                submission.get_absolute_url())

    def test_anonymous_user_cannot_see_filled_pdfs(self):
        self.be_anonymous()
        pdf = self.client.get(reverse('intake-filled_pdf',
                                      kwargs=dict(
                                          submission_id=1
                                      )))
        self.assertRedirects(
            pdf,
            "{}?next={}".format(
                 reverse('user_accounts-login'),
                 reverse('intake-filled_pdf', kwargs={'submission_id': 1})),
            fetch_redirect_response=False
            )

    def test_anonymous_user_cannot_see_submitted_apps(self):
        self.be_anonymous()
        index = self.client.get(reverse('intake-app_index'))
        self.assertRedirects(index,
                             "{}?next={}".format(
                                 reverse('user_accounts-login'),
                                 reverse('intake-app_index')
                             )
                             )

    @skipUnless(DELUXE_TEST, "Super slow, set `DELUXE_TEST=1` to run")
    @patch('intake.notifications.slack_simple.send')
    def test_authenticated_user_can_see_pdf_bundle(self, slack):
        self.be_sfpubdef_user()
        ids = models.FormSubmission.objects.filter(
            organizations=self.sf_pubdef).values_list('pk', flat=True)
        url = url_with_ids('intake-pdf_bundle', ids)
        bundle = self.client.get(url, follow=True)
        self.assertEqual(bundle.status_code, 200)

    @skipUnless(DELUXE_TEST, "Super slow, set `DELUXE_TEST=1` to run")
    @patch('intake.notifications.slack_simple.send')
    def test_staff_user_can_see_pdf_bundle(self, slack):
        self.be_cfa_user()
        submissions = self.sf_pubdef_submissions
        bundle = models.ApplicationBundle.create_with_submissions(
            submissions=submissions,
            organization=self.sf_pubdef)
        ids = [s.id for s in submissions]
        url = url_with_ids('intake-pdf_bundle', ids)
        response = self.client.get(url)
        self.assertRedirects(response, bundle.get_pdf_bundle_url())
        pdf_response = self.client.get(response.url)
        self.assertEqual(pdf_response.status_code, 200)

    @patch('intake.notifications.slack_submissions_viewed.send')
    def test_authenticated_user_can_see_app_bundle(self, slack):
        self.be_cfa_user()
        submissions = self.submissions
        ids = [s.id for s in submissions]
        url = url_with_ids('intake-app_bundle', ids)
        bundle = self.client.get(url)
        self.assertEqual(bundle.status_code, 200)

    @patch(
        'intake.views.session_view_base.notifications'
        '.slack_submissions_deleted.send')
    def test_authenticated_user_can_delete_apps(self, slack):
        self.be_cfa_user()
        submission = self.submissions[0]
        pdf_link = reverse('intake-filled_pdf',
                           kwargs={'submission_id': submission.id})
        url = reverse('intake-delete_page',
                      kwargs={'submission_id': submission.id})
        delete_page = self.client.get(url)
        self.assertEqual(delete_page.status_code, 200)
        after_delete = self.client.fill_form(url)
        self.assertRedirects(after_delete, reverse('intake-app_index'))
        index = self.client.get(after_delete.url)
        self.assertNotContains(index, pdf_link)

    @patch(
        'intake.views.session_view_base.notifications'
        '.slack_submissions_processed.send')
    def test_agency_user_can_mark_apps_as_processed(self, slack):
        self.be_sfpubdef_user()
        submissions = self.sf_pubdef_submissions
        ids = [s.id for s in submissions]
        mark_link = url_with_ids('intake-mark_processed', ids)
        marked = self.client.get(mark_link)
        self.assert_called_once_with_types(
            slack,
            submissions='list',
            user='User')
        self.assertRedirects(marked, reverse('intake-app_index'))
        args, kwargs = slack.call_args
        for sub in kwargs['submissions']:
            self.assertTrue(sub.last_processed_by_agency())
            self.assertIn(sub.id, ids)

    def test_old_urls_return_permanent_redirect(self):
        # redirecting the auth views does not seem necessary
        redirects = {
            '/sanfrancisco/': reverse('intake-apply'),
            '/sanfrancisco/applications/': reverse('intake-app_index'),
        }

        # redirecting the action views (delete, add) does not seem necessary
        id_redirects = {'/sanfrancisco/{}/': 'intake-filled_pdf'}
        multi_id_redirects = {
            '/sanfrancisco/bundle/{}': 'intake-app_bundle',
            '/sanfrancisco/pdfs/{}': 'intake-pdf_bundle'}

        # make some old apps with ids
        old_uuids = [
            '0efd75e8721c4308a8f3247a8c63305d',
            'b873c4ceb1cd4939b1d4c890997ef29c',
            '6cb3887be35543c4b13f27bf83219f4f']
        key_params = '?keys=' + '|'.join(old_uuids)
        ported_models = []
        for uuid in old_uuids:
            instance = mock.FormSubmissionFactory.create(
                old_uuid=uuid)
            ported_models.append(instance)
        ported_models_query = models.FormSubmission.objects.filter(
            old_uuid__in=old_uuids)

        for old, new in redirects.items():
            response = self.client.get(old)
            self.assertRedirects(
                response, new,
                status_code=301, fetch_redirect_response=False)

        for old_template, new_view in id_redirects.items():
            old = old_template.format(old_uuids[2])
            response = self.client.get(old)
            new = reverse(
                new_view, kwargs=dict(
                    submission_id=ported_models[2].id))
            self.assertRedirects(
                response, new,
                status_code=301, fetch_redirect_response=False)

        for old_template, new_view in multi_id_redirects.items():
            old = old_template.format(key_params)
            response = self.client.get(old)
            new = url_with_ids(new_view, [s.id for s in ported_models_query])
            self.assertRedirects(
                response, new,
                status_code=301, fetch_redirect_response=False)
