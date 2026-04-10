import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from authentication.models import LoginAudit
from bank_officer.models import BankOfficerProfile
from credit_prediction.models import CreditPrediction, FraudAlert, LoanApplication
from users.models import CustomUser, FinancialProfile

from .models import AdminActionLog, SystemAnnouncement


TEST_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class AdminPanelWorkflowTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.admin_user = CustomUser.objects.create_user(
            username="risk.admin@creditsense.in",
            email="risk.admin@creditsense.in",
            password="StrongPass123!",
            role="ADMIN",
            first_name="Risk",
            last_name="Admin",
        )
        self.officer_user = CustomUser.objects.create_user(
            username="officer@bankmail.com",
            email="officer@bankmail.com",
            password="StrongPass123!",
            role="BANK_OFFICER",
            first_name="Nisha",
            last_name="Iyer",
        )
        self.officer_profile = BankOfficerProfile.objects.create(
            user=self.officer_user,
            organization_name="ICICI Bank",
            branch_name="Chennai",
            approval_limit=250000,
        )
        self.applicant = CustomUser.objects.create_user(
            username="applicant@creditsense.in",
            email="applicant@creditsense.in",
            password="StrongPass123!",
            role="USER",
            first_name="Arun",
            last_name="Kumar",
        )
        self.financial_profile = FinancialProfile.objects.create(
            user=self.applicant,
            person_age=29,
            person_income=720000,
            person_home_ownership="RENT",
            person_emp_length=5.0,
            cb_person_cred_hist_length=6,
            cb_person_default_on_file="N",
            salary_slip=SimpleUploadedFile(
                "salary-slip.pdf",
                b"%PDF-1.4 admin dashboard test",
                content_type="application/pdf",
            ),
            income_proof_status="PENDING",
        )
        self.application = LoanApplication.objects.create(
            user=self.applicant,
            loan_intent="PERSONAL",
            loan_grade="B",
            loan_amnt=250000,
            loan_int_rate=10.5,
            loan_percent_income=0.25,
            reviewed_by=self.officer_user,
        )
        self.prediction = CreditPrediction.objects.create(
            application=self.application,
            risk_probability=0.22,
            credit_score=705,
            risk_category="Low Risk",
            shap_explanations={"Income": "+24.5", "Credit history": "+13.0"},
            lime_explanations={"Income > threshold": "+0.10"},
            feature_payload={"person_income": 720000, "loan_amnt": 250000},
        )
        self.alert = FraudAlert.objects.create(
            user=self.applicant,
            application=self.application,
            alert_type="Multiple loan applications",
            severity="HIGH",
            description="Repeated submissions detected in a short window.",
            recommended_action="Review manually",
        )
        self.announcement = SystemAnnouncement.objects.create(
            title="Compliance update",
            message="Review salary slips before high-value approvals.",
            audience="BANK_OFFICER",
            created_by=self.admin_user,
        )
        LoginAudit.objects.create(
            user=self.admin_user,
            username_attempt=self.admin_user.username,
            successful=True,
            ip_address="127.0.0.1",
        )
        AdminActionLog.objects.create(
            actor=self.admin_user,
            action_type="ANNOUNCEMENT",
            description="Created a compliance announcement.",
        )
        self.client.login(username="risk.admin@creditsense.in", password="StrongPass123!")

    def test_dashboard_loads_on_admin_prefix(self):
        response = self.client.get(reverse("admin_panel:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(reverse("admin_panel:dashboard"), "/admin/dashboard/")
        self.assertContains(response, "Admin Dashboard")
        self.assertContains(response, "Recent platform activity")

    def test_admin_can_publish_announcement(self):
        response = self.client.post(
            reverse("admin_panel:announcements"),
            {
                "title": "Platform notice",
                "message": "System analytics will refresh tonight.",
                "audience": "ALL",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(SystemAnnouncement.objects.filter(title="Platform notice").exists())
        self.assertTrue(
            AdminActionLog.objects.filter(description__icontains="Platform notice").exists()
        )

    def test_officer_management_updates_profile(self):
        response = self.client.post(
            reverse("admin_panel:officer-management"),
            {
                "profile_id": self.officer_profile.id,
                "organization_name": "ICICI Bank Ltd",
                "employee_id": "ICICI-42",
                "branch_name": "Coimbatore",
                "approval_limit": "500000.00",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.officer_profile.refresh_from_db()
        self.assertEqual(self.officer_profile.organization_name, "ICICI Bank Ltd")
        self.assertEqual(self.officer_profile.branch_name, "Coimbatore")

    def test_application_monitoring_page_loads(self):
        response = self.client.get(reverse("admin_panel:application-monitoring"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Loan Application Monitoring")
        self.assertContains(response, "Arun Kumar")
        self.assertContains(response, "Low Risk")

    def test_activity_logs_page_loads(self):
        response = self.client.get(reverse("admin_panel:activity-logs"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Login attempts")
        self.assertContains(response, "Created a compliance announcement.")
