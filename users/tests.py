import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from admin_panel.models import SystemAnnouncement
from credit_prediction.models import CreditPrediction, FraudAlert, LoanApplication

from .models import CustomUser, FinancialProfile

TEST_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class UserWorkflowTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="ananya.sharma@creditsense.ai",
            email="ananya.sharma@creditsense.ai",
            password="StrongPass123",
            role="USER",
            first_name="Ananya",
            last_name="Sharma",
        )
        self.admin = CustomUser.objects.create_user(
            username="admin@creditsense.ai",
            email="admin@creditsense.ai",
            password="StrongPass123",
            role="ADMIN",
        )
        self.officer = CustomUser.objects.create_user(
            username="officer@creditsense.ai",
            email="officer@creditsense.ai",
            password="StrongPass123",
            role="BANK_OFFICER",
            first_name="Rahul",
            last_name="Verma",
        )
        FinancialProfile.objects.create(
            user=self.user,
            person_age=29,
            person_income=72000,
            person_home_ownership="RENT",
            person_emp_length=5.0,
            cb_person_cred_hist_length=6,
            cb_person_default_on_file="N",
        )
        self.application = LoanApplication.objects.create(
            user=self.user,
            loan_intent="PERSONAL",
            loan_grade="B",
            loan_amnt=9000,
            loan_int_rate=11.2,
            loan_percent_income=0.18,
            status="VERIFICATION_REQUIRED",
            reviewed_by=self.officer,
            decision_notes="Need updated income proof.",
            reviewed_at=timezone.now(),
        )
        self.prediction = CreditPrediction.objects.create(
            application=self.application,
            risk_probability=0.29,
            credit_score=691,
            risk_category="Low Risk",
            shap_explanations={"Income": "+24.0", "Credit history": "+14.0"},
            lime_explanations={"Income > threshold": "+0.102"},
            feature_payload={"Income": 72000, "Credit history": 6},
        )
        FraudAlert.objects.create(
            user=self.user,
            application=self.application,
            alert_type="Multiple loan requests",
            severity="MEDIUM",
            description="A similar request was submitted recently.",
            recommended_action="Review submission activity",
        )
        SystemAnnouncement.objects.create(
            title="Applicant notice",
            message="Upload accurate financial information before running a new prediction.",
            audience="USER",
            created_by=self.admin,
        )
        self.client.login(
            username="ananya.sharma@creditsense.ai",
            password="StrongPass123",
        )

    def test_dashboard_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("users:dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_loads_for_authenticated_user(self):
        response = self.client.get(reverse("users:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Welcome back, Ananya!")
        self.assertContains(response, "Low Risk")
        self.assertNotContains(
            response,
            "You have a completed credit analysis. Your profile is updated and ready for review.",
        )

    def test_financial_data_page_hides_only_derived_loan_fields(self):
        response = self.client.get(reverse("users:financial-data"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Apply for Loan")
        self.assertContains(response, "income-proof-widget", html=False)
        self.assertContains(response, "current-document-card", html=False)
        self.assertNotContains(response, 'name="loan-loan_grade"', html=False)
        self.assertNotContains(response, 'name="loan-loan_amnt"', html=False)
        self.assertContains(response, 'name="loan-loan_percent_income"', html=False)
        self.assertContains(response, 'data-auto-calculated="true"', html=False)
        self.assertNotContains(response, "Live Risk Preview")

    def test_financial_data_submission_auto_calculates_income_ratio(self):
        response = self.client.post(
            reverse("users:financial-data"),
            {
                "profile-person_age": 30,
                "profile-monthly_income": 6500,
                "profile-person_home_ownership": "RENT",
                "profile-person_emp_length": 6.0,
                "profile-cb_person_cred_hist_length": 7,
                "profile-cb_person_default_on_file": "N",
                "profile-salary_slip": SimpleUploadedFile(
                    "ananya-sharma-salary-slip.pdf",
                    b"%PDF-1.4 test salary slip",
                    content_type="application/pdf",
                ),
                "loan-loan_intent": "MEDICAL",
                "loan-loan_int_rate": 10.1,
                "loan-loan_percent_income": 0.99,
            },
        )

        latest_prediction = CreditPrediction.objects.filter(application__user=self.user).latest(
            "created_at"
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("users:credit-score"),
            response.url,
        )
        self.assertEqual(latest_prediction.application.loan_intent, "MEDICAL")
        self.assertEqual(latest_prediction.application.loan_percent_income, 0.16)
        self.assertEqual(latest_prediction.application.loan_amnt, 12480.0)
        self.assertEqual(latest_prediction.application.loan_grade, "B")
        self.user.refresh_from_db()
        self.assertEqual(self.user.financial_profile.income_proof_status, "PENDING")

    def test_credit_score_page_loads(self):
        response = self.client.get(reverse("users:credit-score"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your Credit Risk Analysis")
        self.assertContains(response, "Credit Score")
        self.assertContains(response, "Officer Review Update")
        self.assertContains(response, "Need updated income proof.")
        self.assertContains(response, "691")
        self.assertNotContains(response, "Community Benchmark")
        self.assertNotContains(response, "Global Avg.")
        self.assertNotContains(response, "Top 15%")

    def test_explanation_page_loads(self):
        response = self.client.get(reverse("users:explanation"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Explainable AI Insights")
        self.assertContains(response, "SHAP summarizes feature impact")
        self.assertContains(response, "SHAP highlights which features pushed your score higher or lower")
        self.assertContains(response, "LIME explains why this specific prediction was made")
        self.assertContains(response, "Point-wise explanation", count=2)
        self.assertNotContains(response, "Point-wise SHAP Explanation")
        self.assertNotContains(response, "Point-wise LIME Explanation")
        self.assertNotContains(response, "About Each SHAP Item")
        self.assertNotContains(response, "About Each LIME Item")
        self.assertContains(response, "Income pushed the model outcome upward in the SHAP view")
        self.assertContains(response, "This local rule pushed the current prediction upward in the LIME view")
        self.assertContains(response, "Income")
        self.assertNotContains(response, "Automated AI Verdict")
        self.assertNotContains(response, "peer datasets")

    def test_improvements_page_loads(self):
        response = self.client.get(reverse("users:improvements"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Credit Improvement Suggestions")
        self.assertNotContains(response, "AI synthesized these behavioral shifts")

    def test_fraud_alerts_page_uses_database_records(self):
        response = self.client.get(reverse("users:fraud-alerts"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Open Alerts")
        self.assertContains(response, "Alert Filter")
        self.assertContains(response, "Multiple loan requests")

    def test_fraud_alerts_page_shows_empty_state_when_no_records_exist(self):
        FraudAlert.objects.filter(user=self.user).delete()

        response = self.client.get(reverse("users:fraud-alerts"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No fraud alerts right now")
        self.assertContains(response, "Run new analysis")

    def test_notifications_page_uses_database_records(self):
        response = self.client.get(reverse("users:notifications"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Applicant notice")
        self.assertContains(response, "Credit analysis completed")
        self.assertContains(response, "Need updated income proof.")
        self.assertContains(response, "Reviewed by Rahul Verma")
        self.assertNotContains(response, "Subscribe for Updates")

    def test_documents_page_uses_only_real_document_data(self):
        response = self.client.get(reverse("users:documents"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Document Center")
        self.assertContains(response, "Income Proof")
        self.assertNotContains(response, "Identity Proof")
        self.assertNotContains(response, "Bank Log")

    def test_history_page_shows_officer_decision_update(self):
        response = self.client.get(reverse("users:history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Need updated income proof.")
        self.assertContains(response, "Rahul Verma")

    def test_profile_page_loads(self):
        response = self.client.get(reverse("users:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profile & Settings")
