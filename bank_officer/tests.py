import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from admin_panel.models import SystemAnnouncement
from bank_officer.models import BankOfficerProfile
from credit_prediction.models import CreditPrediction, FraudAlert, LoanApplication
from users.models import CustomUser, FinancialProfile


TEST_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class BankOfficerWorkflowTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.officer = CustomUser.objects.create_user(
            username="officer",
            email="officer@bankmail.com",
            password="StrongPass123",
            role="BANK_OFFICER",
            first_name="Priya",
            last_name="Rao",
        )
        BankOfficerProfile.objects.create(
            user=self.officer,
            organization_name="State Bank of India",
            branch_name="Chennai Credit Hub",
        )
        self.admin = CustomUser.objects.create_user(
            username="admin",
            email="admin@creditsense.ai",
            password="StrongPass123",
            role="ADMIN",
        )
        self.applicant = CustomUser.objects.create_user(
            username="borrower",
            email="borrower@creditsense.ai",
            password="StrongPass123",
            role="USER",
            first_name="Arjun",
            last_name="Mehta",
        )
        FinancialProfile.objects.create(
            user=self.applicant,
            person_age=31,
            person_income=62000,
            person_home_ownership="RENT",
            person_emp_length=6.0,
            cb_person_cred_hist_length=7,
            cb_person_default_on_file="N",
            salary_slip=SimpleUploadedFile(
                "salary-slip.pdf",
                b"%PDF-1.4 officer review test",
                content_type="application/pdf",
            ),
            income_proof_status="PENDING",
        )
        self.application = LoanApplication.objects.create(
            user=self.applicant,
            loan_intent="PERSONAL",
            loan_grade="C",
            loan_amnt=8500,
            loan_int_rate=10.5,
            loan_percent_income=0.2,
        )
        self.prediction = CreditPrediction.objects.create(
            application=self.application,
            risk_probability=0.31,
            credit_score=679,
            risk_category="Medium Risk",
            shap_explanations={"Income": "+18.0", "Credit history": "+12.0"},
            lime_explanations={"Income > threshold": "+0.120"},
            feature_payload={"Income": 62000, "Credit history": 7},
        )
        self.alert = FraudAlert.objects.create(
            user=self.applicant,
            application=self.application,
            alert_type="Multiple loan applications",
            severity="HIGH",
            description="Repeated submissions detected in a short review window.",
            recommended_action="Review supporting documents",
        )
        SystemAnnouncement.objects.create(
            title="Policy reminder",
            message="Recheck identity documents before approving medium-risk applications.",
            audience="BANK_OFFICER",
            created_by=self.admin,
        )
        self.client.login(username="officer", password="StrongPass123")

    def test_dashboard_loads_for_officer(self):
        response = self.client.get(reverse("bank_officer:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bank Officer Dashboard")
        self.assertContains(response, "Recent applicant activity")

    def test_applications_page_filters_by_risk_category(self):
        response = self.client.get(
            reverse("bank_officer:applications"),
            {"risk": "Medium Risk"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Arjun Mehta")
        self.assertContains(response, "Medium Risk")

    def test_risk_analysis_detail_page_loads(self):
        response = self.client.get(
            reverse("bank_officer:risk-analysis-detail", args=[self.application.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Risk Analysis for Application")
        self.assertContains(response, "Medium Risk")

    def test_explanation_detail_page_loads(self):
        response = self.client.get(
            reverse("bank_officer:explanation-detail", args=[self.application.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SHAP contributions")
        self.assertContains(response, "Income")

    def test_fraud_alerts_page_uses_display_alias_for_legacy_alert_names(self):
        FraudAlert.objects.create(
            user=self.applicant,
            application=self.application,
            alert_type="Unusual transactions",
            severity="CRITICAL",
            description="Exposure is unusually high for this profile.",
            recommended_action="Request manual underwriting review",
        )

        response = self.client.get(reverse("bank_officer:fraud-alerts"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fraud Alerts")
        self.assertContains(response, "High liability exposure")
        self.assertNotContains(response, "Unusual transactions")

    def test_officer_can_review_application_from_overview(self):
        response = self.client.post(
            reverse("bank_officer:application-detail", args=[self.application.id]),
            {"decision": "APPROVED", "decision_notes": "Looks acceptable."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("decision_saved=1", response["Location"])
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "APPROVED")

    def test_application_detail_shows_saved_state_after_quick_decision_redirect(self):
        response = self.client.get(
            f"{reverse('bank_officer:application-detail', args=[self.application.id])}?decision_saved=1"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Decision saved.")
        self.assertContains(response, "Saved")

    def test_officer_can_request_additional_verification(self):
        response = self.client.post(
            reverse("bank_officer:decision", args=[self.application.id]),
            {
                "decision": "VERIFICATION_REQUIRED",
                "decision_notes": "Need updated income proof.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "VERIFICATION_REQUIRED")
        self.assertEqual(self.application.reviewed_by, self.officer)

    def test_applicant_profile_page_loads(self):
        response = self.client.get(
            reverse("bank_officer:applicant-profile", args=[self.applicant.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Applicant Profile")
        self.assertContains(response, "Arjun Mehta")

    def test_notifications_page_uses_database_records(self):
        response = self.client.get(reverse("bank_officer:notifications"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Policy reminder")
        self.assertContains(response, "Multiple loan applications")

    def test_officer_can_update_income_proof_status(self):
        response = self.client.post(
            reverse("bank_officer:application-detail", args=[self.application.id]),
            {"income_proof_status": "VERIFIED"},
        )

        self.assertEqual(response.status_code, 302)
        self.applicant.financial_profile.refresh_from_db()
        self.assertEqual(
            self.applicant.financial_profile.income_proof_status,
            "VERIFIED",
        )
