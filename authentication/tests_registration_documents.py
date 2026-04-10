import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from authentication.forms import EMPLOYMENT_DOCUMENT_REQUIREMENTS, RegisterForm
from users.models import (
    ApplicantEmploymentDocument,
    ApplicantProfile,
    CustomUser,
    FinancialProfile,
)


TEST_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class RegistrationDocumentValidationTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.register_url = reverse("register")

    def _base_payload(self, **overrides):
        payload = {
            "first_name": "Aarav",
            "last_name": "Sharma",
            "dob": "1998-05-10",
            "gender": "MALE",
            "marital_status": "SINGLE",
            "email": "aarav.sharma@creditsense.ai",
            "mobile_number": "9876543210",
            "residential_address": "12 Lake View Road",
            "city": "Chennai",
            "state": "TN",
            "pin_code": "600001",
            "employment_type": "SALARIED_PRIVATE",
            "employer_name": "Blue Orbit Tech",
            "salary_bank": "HDFC Bank",
            "monthly_salary": "45000",
            "loan_amount_requested": "200000",
            "loan_purpose": "HOME",
            "existing_emis": "4000",
            "num_dependants": "1",
            "aadhaar_number": "123456789012",
            "pan_number": "ABCDE1234F",
            "password": "SecurePass123!",
            "confirm_password": "SecurePass123!",
        }
        payload.update(overrides)
        return payload

    def _payload_for_employment_type(self, employment_type, **overrides):
        payload = self._base_payload(
            employment_type=employment_type,
            email=f"{employment_type.lower()}@creditsense.ai",
        )

        if employment_type in {"SALARIED_GOVT", "SALARIED_PRIVATE"}:
            payload.update(
                {
                    "employer_name": "Verified Employer",
                    "monthly_salary": "48000",
                }
            )
        elif employment_type in {
            "SELF_EMPLOYED_PROFESSIONAL",
            "SELF_EMPLOYED_BUSINESS",
        }:
            payload.update(
                {
                    "employer_name": "",
                    "monthly_salary": "",
                    "business_name": "Aarav Advisory",
                    "annual_income": "720000",
                    "years_in_business": "4",
                }
            )
        elif employment_type in {
            "DAILY_WAGE",
            "FARMER",
            "SEASONAL",
            "GIG_WORKER",
            "PENSIONER",
            "NRI",
        }:
            payload.update(
                {
                    "employer_name": "",
                    "monthly_salary": "",
                    "average_monthly_income": "26000",
                }
            )
        elif employment_type == "HOMEMAKER":
            payload.update(
                {
                    "employer_name": "",
                    "monthly_salary": "",
                    "has_co_applicant": "on",
                    "co_applicant_name": "Rohan Sharma",
                    "co_applicant_relationship": "Spouse",
                    "co_applicant_income": "52000",
                }
            )
        elif employment_type == "STUDENT_UNEMPLOYED":
            payload.update(
                {
                    "employer_name": "",
                    "monthly_salary": "",
                    "guarantor_name": "Mahesh Kumar",
                    "guarantor_contact": "9123456789",
                    "guarantor_income": "55000",
                }
            )

        payload.update(overrides)
        return payload

    def _pdf_file(self, file_name):
        return SimpleUploadedFile(
            file_name,
            b"%PDF-1.4 sample document",
            content_type="application/pdf",
        )

    def test_government_salaried_registration_requires_both_documents(self):
        form = RegisterForm(
            data=self._base_payload(
                employment_type="SALARIED_GOVT",
                email="govt.user@creditsense.ai",
                employer_name="Government School",
                monthly_salary="38000",
            ),
            files={
                "employment_document_primary": SimpleUploadedFile(
                    "salary-slip.pdf",
                    b"%PDF-1.4 salary slip",
                    content_type="application/pdf",
                )
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("employment_document_secondary", form.errors)
        self.assertEqual(
            form.errors["employment_document_secondary"][0],
            "Upload Form 16 to continue.",
        )

    def test_gig_worker_registration_requires_platform_income_statement(self):
        form = RegisterForm(
            data=self._base_payload(
                employment_type="GIG_WORKER",
                email="gig.worker@creditsense.ai",
                employer_name="",
                monthly_salary="",
                average_monthly_income="22000",
            ),
        )

        self.assertFalse(form.is_valid())
        self.assertIn("employment_document_primary", form.errors)
        self.assertEqual(
            form.errors["employment_document_primary"][0],
            "Upload Platform Income Statement to continue.",
        )

    def test_each_employment_type_requires_its_exact_document_set(self):
        for employment_type, config in EMPLOYMENT_DOCUMENT_REQUIREMENTS.items():
            with self.subTest(employment_type=employment_type):
                form = RegisterForm(
                    data=self._payload_for_employment_type(employment_type),
                )

                self.assertFalse(form.is_valid())
                self.assertEqual(
                    form.cleaned_data["missing_document_fields"],
                    [doc["type"] for doc in config["documents"]],
                )

                primary_error = form.errors["employment_document_primary"][0]
                self.assertEqual(
                    primary_error,
                    f"Upload {config['documents'][0]['label']} to continue.",
                )

                if len(config["documents"]) > 1:
                    secondary_error = form.errors["employment_document_secondary"][0]
                    self.assertEqual(
                        secondary_error,
                        f"Upload {config['documents'][1]['label']} to continue.",
                    )
                else:
                    self.assertNotIn("employment_document_secondary", form.errors)

    def test_registration_saves_documents_and_allows_progress(self):
        response = self.client.post(
            self.register_url,
            data={
                **self._base_payload(),
                "employment_document_primary": SimpleUploadedFile(
                    "salary-slip.pdf",
                    b"%PDF-1.4 salary slip",
                    content_type="application/pdf",
                ),
                "employment_document_secondary": SimpleUploadedFile(
                    "bank-statement.pdf",
                    b"%PDF-1.4 bank statement",
                    content_type="application/pdf",
                ),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)

        user = CustomUser.objects.get(email="aarav.sharma@creditsense.ai")
        applicant_profile = ApplicantProfile.objects.get(user=user)
        financial_profile = FinancialProfile.objects.get(user=user)

        self.assertTrue(applicant_profile.employment_document_primary.name)
        self.assertTrue(applicant_profile.employment_document_secondary.name)
        self.assertEqual(
            ApplicantEmploymentDocument.objects.filter(user=user).count(),
            2,
        )
        self.assertEqual(
            financial_profile.salary_slip.name,
            applicant_profile.employment_document_primary.name,
        )
        self.assertEqual(financial_profile.income_proof_status, "PENDING")

    def test_registration_json_error_returns_missing_document_types(self):
        response = self.client.post(
            self.register_url,
            data=self._base_payload(email="json.missing@creditsense.ai"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "missing_documents")
        self.assertEqual(
            response.json()["fields"],
            [
                "salary_slip_latest_3_months",
                "bank_statement_last_6_months",
            ],
        )

    def test_invalid_document_format_returns_validation_error_not_missing_documents(self):
        response = self.client.post(
            self.register_url,
            data={
                **self._payload_for_employment_type(
                    "SALARIED_PRIVATE",
                    email="invalid-format@creditsense.ai",
                ),
                "employment_document_primary": SimpleUploadedFile(
                    "salary-slip.txt",
                    b"plain text",
                    content_type="text/plain",
                ),
                "employment_document_secondary": self._pdf_file("bank-statement.pdf"),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["error"], "validation_error")
        self.assertIn("employment_document_primary", payload["fields"])
        self.assertEqual(
            payload["fields"]["employment_document_primary"][0]["message"],
            "Only PDF, JPG, PNG files are accepted",
        )

    def test_single_document_employment_type_discards_irrelevant_secondary_upload(self):
        response = self.client.post(
            self.register_url,
            data={
                **self._payload_for_employment_type(
                    "SEASONAL",
                    email="seasonal.worker@creditsense.ai",
                ),
                "employment_document_primary": self._pdf_file("seasonal-proof.pdf"),
                "employment_document_secondary": self._pdf_file("extra-document.pdf"),
            },
        )

        self.assertEqual(response.status_code, 302)
        user = CustomUser.objects.get(email="seasonal.worker@creditsense.ai")
        applicant_profile = ApplicantProfile.objects.get(user=user)

        self.assertTrue(applicant_profile.employment_document_primary.name)
        self.assertFalse(applicant_profile.employment_document_secondary)
        self.assertEqual(
            list(
                ApplicantEmploymentDocument.objects.filter(user=user).values_list(
                    "document_type", flat=True
                )
            ),
            ["seasonal_income_declaration"],
        )
