import json
import shutil
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from admin_panel.models import AdminActionLog, SystemAnnouncement
from authentication.models import LoginAudit
from bank_officer.models import BankOfficerProfile
from credit_prediction.models import CreditPrediction, FraudAlert, LoanApplication
from users.models import CustomUser, FinancialProfile


TEST_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class AdminApiWorkflowTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.admin_user = CustomUser.objects.create_user(
            username="admin.operations@creditsense.in",
            email="admin.operations@creditsense.in",
            password="CreditSense@Admin2026!",
            role="ADMIN",
            first_name="Platform",
            last_name="Admin",
            is_staff=True,
            is_superuser=True,
        )
        self.officer_user = CustomUser.objects.create_user(
            username="officer.icici@creditsense.in",
            email="officer.icici@creditsense.in",
            password="StrongPass123!",
            role="BANK_OFFICER",
            first_name="Neha",
            last_name="Menon",
        )
        self.officer_profile = BankOfficerProfile.objects.create(
            user=self.officer_user,
            organization_name="ICICI Bank",
            employee_id="ICICI-001",
            branch_name="Kochi",
            approval_limit=450000,
        )
        self.applicant = CustomUser.objects.create_user(
            username="arun.kumar@creditsense.in",
            email="arun.kumar@creditsense.in",
            password="StrongPass123!",
            role="USER",
            first_name="Arun",
            last_name="Kumar",
        )
        self.financial_profile = FinancialProfile.objects.create(
            user=self.applicant,
            person_age=29,
            person_income=840000,
            person_home_ownership="RENT",
            person_emp_length=4.5,
            cb_person_cred_hist_length=6,
            cb_person_default_on_file="N",
            salary_slip=SimpleUploadedFile(
                "salary-slip.pdf",
                b"%PDF-1.4 creditsense api test",
                content_type="application/pdf",
            ),
            income_proof_status="PENDING",
        )
        self.application = LoanApplication.objects.create(
            user=self.applicant,
            loan_intent="PERSONAL",
            loan_grade="B",
            loan_amnt=300000,
            loan_int_rate=10.75,
            loan_percent_income=0.36,
            reviewed_by=self.officer_user,
        )
        self.prediction = CreditPrediction.objects.create(
            application=self.application,
            risk_probability=0.31,
            credit_score=688,
            risk_category="Medium Risk",
            shap_explanations={"Income": "+22.0", "Debt load": "-13.0"},
            lime_explanations={"Debt load high": "-0.11"},
            feature_payload={"person_income": 840000, "loan_amnt": 300000},
        )
        self.alert = FraudAlert.objects.create(
            user=self.applicant,
            application=self.application,
            alert_type="Multiple loan applications",
            severity="HIGH",
            description="Applicant attempted several credit checks in a short window.",
            recommended_action="Review manually before approval",
        )
        self.announcement = SystemAnnouncement.objects.create(
            title="Policy update",
            message="Re-check salary slips for applications above Rs. 2,50,000.",
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
            description="Created the initial policy update.",
        )

    def test_api_login_accepts_shared_identifier_field(self):
        response = self.client.post(
            reverse("api-login"),
            data=json.dumps(
                {
                    "identifier": "admin.operations@creditsense.in",
                    "password": "CreditSense@Admin2026!",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], "ADMIN")

    def test_admin_dashboard_and_analytics_endpoints_return_page_payloads(self):
        self.client.login(
            username="admin.operations@creditsense.in",
            password="CreditSense@Admin2026!",
        )

        dashboard_response = self.client.get(reverse("api-admin-dashboard"))
        analytics_response = self.client.get(reverse("api-admin-analytics"))
        logs_response = self.client.get(reverse("api-admin-activity-logs"))

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn("totals", dashboard_response.json())
        self.assertIn("summary", dashboard_response.json())
        self.assertIn("recent_activity", dashboard_response.json())
        self.assertEqual(analytics_response.status_code, 200)
        self.assertIn("risk_chart_data", analytics_response.json())
        self.assertIn("application_chart_data", analytics_response.json())
        self.assertEqual(logs_response.status_code, 200)
        self.assertIn("summary", logs_response.json())
        self.assertTrue(logs_response.json()["login_audits"])

    def test_admin_user_and_officer_management_endpoints_work(self):
        self.client.login(
            username="admin.operations@creditsense.in",
            password="CreditSense@Admin2026!",
        )

        users_response = self.client.get(reverse("api-admin-users"))
        create_officer_response = self.client.post(
            reverse("api-admin-officers"),
            data=json.dumps(
                {
                    "full_name": "Rahul Nair",
                    "email": "rahul.nair@sbi.co.in",
                    "password": "OfficerPass123!",
                    "organization_name": "State Bank of India",
                    "employee_id": "SBI-2201",
                    "branch_name": "Thiruvananthapuram",
                    "approval_limit": "650000.00",
                    "is_active": True,
                }
            ),
            content_type="application/json",
        )

        created_profile = BankOfficerProfile.objects.get(employee_id="SBI-2201")
        update_response = self.client.patch(
            reverse("api-admin-officer-detail", args=[created_profile.id]),
            data=json.dumps(
                {
                    "branch_name": "Kozhikode",
                    "approval_limit": "700000.00",
                    "is_active": False,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(users_response.status_code, 200)
        self.assertIn("results", users_response.json())
        self.assertIn("summary", users_response.json())
        self.assertEqual(create_officer_response.status_code, 201)
        self.assertEqual(update_response.status_code, 200)
        created_profile.refresh_from_db()
        self.assertEqual(created_profile.branch_name, "Kozhikode")
        self.assertFalse(created_profile.user.is_active)

    def test_admin_monitoring_and_announcement_endpoints_work(self):
        self.client.login(
            username="admin.operations@creditsense.in",
            password="CreditSense@Admin2026!",
        )

        applications_response = self.client.get(reverse("api-admin-applications"))
        fraud_response = self.client.get(reverse("api-admin-fraud-alerts"))
        resolve_response = self.client.post(
            reverse("api-admin-fraud-alert-resolve", args=[self.alert.id])
        )
        announcement_create_response = self.client.post(
            reverse("api-admin-announcements"),
            data=json.dumps(
                {
                    "title": "Security notice",
                    "message": "Monitor repeated repayment profile changes closely.",
                    "audience": "ALL",
                    "is_active": True,
                }
            ),
            content_type="application/json",
        )
        announcement_detail_response = self.client.patch(
            reverse("api-admin-announcement-detail", args=[self.announcement.id]),
            data=json.dumps({"is_active": False}),
            content_type="application/json",
        )

        self.assertEqual(applications_response.status_code, 200)
        self.assertIn("results", applications_response.json())
        self.assertEqual(fraud_response.status_code, 200)
        self.assertEqual(fraud_response.json()["summary"]["open_count"], 1)
        self.assertEqual(resolve_response.status_code, 200)
        self.alert.refresh_from_db()
        self.assertTrue(self.alert.resolved)
        self.assertEqual(announcement_create_response.status_code, 201)
        self.assertEqual(announcement_detail_response.status_code, 200)
        self.announcement.refresh_from_db()
        self.assertFalse(self.announcement.is_active)

    def test_non_admin_cannot_access_admin_api(self):
        self.client.login(
            username="officer.icici@creditsense.in",
            password="StrongPass123!",
        )

        response = self.client.get(reverse("api-admin-dashboard"))

        self.assertEqual(response.status_code, 403)

    def test_applicant_prediction_api_accepts_current_minimal_payload(self):
        self.client.login(
            username="arun.kumar@creditsense.in",
            password="StrongPass123!",
        )

        with patch(
            "api.views.create_prediction_workflow",
            return_value=(self.application, self.prediction),
        ) as mocked_workflow:
            response = self.client.post(
                reverse("api-predictions"),
                data=json.dumps(
                    {
                        "person_age": 29,
                        "monthly_income": 70000,
                        "person_home_ownership": "RENT",
                        "person_emp_length": 4.5,
                        "cb_person_cred_hist_length": 6,
                        "cb_person_default_on_file": "N",
                        "loan_intent": "PERSONAL",
                        "loan_int_rate": 10.75,
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 201)
        mocked_workflow.assert_called_once()
        called_user, profile_data, application_data = mocked_workflow.call_args[0]
        self.assertEqual(called_user, self.applicant)
        self.assertEqual(profile_data["person_income"], 840000)
        self.assertEqual(application_data["loan_intent"], "PERSONAL")
        self.assertEqual(application_data["loan_int_rate"], 10.75)
        self.assertNotIn("loan_grade", application_data)
        self.assertNotIn("loan_amnt", application_data)
        self.assertNotIn("loan_percent_income", application_data)
        self.assertEqual(response.json()["prediction"]["id"], self.prediction.id)

    def test_applicant_can_access_only_own_user_api_endpoints(self):
        self.client.login(
            username="arun.kumar@creditsense.in",
            password="StrongPass123!",
        )

        predictions_response = self.client.get(reverse("api-predictions"))
        prediction_detail_response = self.client.get(
            reverse("api-prediction-detail", args=[self.prediction.id])
        )
        explanations_response = self.client.get(
            reverse("api-explanations", args=[self.prediction.id])
        )
        officer_queue_response = self.client.get(reverse("api-officer-applications"))

        self.assertEqual(predictions_response.status_code, 200)
        self.assertEqual(len(predictions_response.json()), 1)
        self.assertEqual(prediction_detail_response.status_code, 200)
        self.assertEqual(
            prediction_detail_response.json()["credit_score"],
            self.prediction.credit_score,
        )
        self.assertEqual(explanations_response.status_code, 200)
        self.assertIn("shap_explanations", explanations_response.json())
        self.assertEqual(officer_queue_response.status_code, 403)

    def test_officer_can_access_officer_api_endpoints(self):
        self.client.login(
            username="officer.icici@creditsense.in",
            password="StrongPass123!",
        )

        applications_response = self.client.get(reverse("api-officer-applications"))
        decision_response = self.client.post(
            reverse("api-officer-decision", args=[self.application.id]),
            data=json.dumps(
                {
                    "decision": "VERIFICATION_REQUIRED",
                    "decision_notes": "Need refreshed income proof.",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(applications_response.status_code, 200)
        self.assertEqual(len(applications_response.json()), 1)
        self.assertEqual(decision_response.status_code, 200)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, "VERIFICATION_REQUIRED")
        self.assertEqual(self.application.reviewed_by, self.officer_user)
