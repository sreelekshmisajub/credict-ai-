from django.test import TestCase
from django.urls import reverse

from users.models import CustomUser


class AuthenticationFlowTests(TestCase):
    def setUp(self):
        self.register_url = reverse("register")
        self.login_url = reverse("login")
        self.admin_login_url = reverse("admin-login")

    def test_register_page_exposes_employment_document_config(self):
        response = self.client.get(self.register_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'employment-document-requirements', html=False)
        self.assertContains(response, "Exact required documents", html=False)
        self.assertContains(response, "Required Documents for Your Employment Type", html=False)
        self.assertContains(response, "Co-applicant details", html=False)
        self.assertContains(response, "Guarantor details", html=False)

    def test_login_page_renders_email_field(self):
        response = self.client.get(self.login_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="email"', html=False)
        self.assertContains(response, 'autocomplete="email"', html=False)

    def test_admin_login_route_redirects_to_shared_login_page(self):
        response = self.client.get(self.admin_login_url)

        self.assertRedirects(
            response,
            self.login_url,
            fetch_redirect_response=False,
        )

    def test_public_login_redirects_admin_to_admin_dashboard(self):
        CustomUser.objects.create_user(
            username="admin.ops@creditsense.ai",
            email="admin.ops@creditsense.ai",
            password="SecurePass123!",
            role="ADMIN",
        )

        response = self.client.post(
            self.login_url,
            {
                "email": "admin.ops@creditsense.ai",
                "password": "SecurePass123!",
            },
        )

        self.assertRedirects(
            response,
            reverse("admin_panel:dashboard"),
            fetch_redirect_response=False,
        )

    def test_public_login_redirects_bank_officer_to_officer_dashboard(self):
        CustomUser.objects.create_user(
            username="officer@bankmail.com",
            email="officer@bankmail.com",
            password="SecurePass123!",
            role="BANK_OFFICER",
        )

        response = self.client.post(
            self.login_url,
            {
                "email": "officer@bankmail.com",
                "password": "SecurePass123!",
            },
        )

        self.assertRedirects(
            response,
            reverse("bank_officer:dashboard"),
            fetch_redirect_response=False,
        )
