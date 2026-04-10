import re

from django import forms
from django.contrib.auth import authenticate
from django.utils import timezone

from users.models import ApplicantEmploymentDocument, ApplicantProfile, CustomUser


EMPLOYMENT_DOCUMENT_REQUIREMENTS = {
    "SALARIED_GOVT": {
        "employment_label": "Salaried (Govt/PSU)",
        "note": "Upload salary slip for the latest 3 months and your most recent Form 16.",
        "documents": [
            {
                "type": "salary_slip_latest_3_months",
                "label": "Salary Slip (Latest 3 Months)",
                "description": "Upload your most recent 3 months' salary slips issued by your government or PSU employer.",
            },
            {
                "type": "form_16",
                "label": "Form 16",
                "description": "Upload your latest Form 16 (TDS certificate) issued by your employer.",
            },
        ],
    },
    "SALARIED_PRIVATE": {
        "employment_label": "Salaried (Private)",
        "note": "Upload your latest salary slip and last 6 months' bank statement from your salary account.",
        "documents": [
            {
                "type": "salary_slip_latest_3_months",
                "label": "Salary Slip (Latest 3 Months)",
                "description": "Upload your most recent 3 months' salary slips from your private employer.",
            },
            {
                "type": "bank_statement_last_6_months",
                "label": "Bank Statement (Last 6 Months)",
                "description": "Upload your salary account bank statement for the last 6 months.",
            },
        ],
    },
    "SELF_EMPLOYED_PROFESSIONAL": {
        "employment_label": "Self-Employed Professional",
        "note": "Applicable for Doctors, CAs, Consultants, and other licensed professionals.",
        "documents": [
            {
                "type": "itr_last_2_years",
                "label": "ITR \u2013 Income Tax Return (Last 2 Years)",
                "description": "Upload your filed ITR documents for the last 2 financial years.",
            },
            {
                "type": "bank_statement_last_6_months",
                "label": "Bank Statement (Last 6 Months)",
                "description": "Upload your primary business or personal bank statement for the last 6 months.",
            },
        ],
    },
    "SELF_EMPLOYED_BUSINESS": {
        "employment_label": "Self-Employed Business",
        "note": "Applicable for shop owners, traders, and registered business owners.",
        "documents": [
            {
                "type": "gst_returns_last_2_years",
                "label": "GST Returns (Last 2 Years)",
                "description": "Upload your GST return filings for the last 2 financial years.",
            },
            {
                "type": "profit_and_loss_statement",
                "label": "Profit & Loss Statement (P&L)",
                "description": "Upload your business Profit & Loss statement certified by a CA or accountant.",
            },
        ],
    },
    "DAILY_WAGE": {
        "employment_label": "Daily Wage Worker",
        "note": "Bank/UPI history and an employer letter are required to verify irregular income patterns.",
        "documents": [
            {
                "type": "bank_upi_transaction_history_last_3_months",
                "label": "Bank / UPI Transaction History (Last 3 Months)",
                "description": "Upload a bank passbook printout or UPI transaction history screenshot for the last 3 months.",
            },
            {
                "type": "employer_letter_signed",
                "label": "Employer Letter",
                "description": "Upload a signed letter from your current or most recent employer confirming your engagement.",
            },
        ],
    },
    "FARMER": {
        "employment_label": "Agricultural / Farmer",
        "note": "Both the 7/12 land extract and Kisan Card are mandatory for agricultural income verification.",
        "documents": [
            {
                "type": "land_record_7_12_extract",
                "label": "7/12 Extract (Land Record)",
                "description": "Upload the official 7/12 extract (Satbara Utara) from your state revenue department.",
            },
            {
                "type": "kisan_card",
                "label": "Kisan Card",
                "description": "Upload a clear scan or photo of your Kisan Credit Card or Kisan ID issued by the bank or government.",
            },
        ],
    },
    "SEASONAL": {
        "employment_label": "Seasonal Worker",
        "note": "A seasonal income declaration is required. Only one document is mandatory for this employment type.",
        "documents": [
            {
                "type": "seasonal_income_declaration",
                "label": "Seasonal Income Declaration",
                "description": "Upload a self-declared or authorized seasonal income declaration letter stating your occupation, season, and estimated income.",
            },
        ],
    },
    "GIG_WORKER": {
        "employment_label": "Gig Worker",
        "note": "Applicable for Ola, Uber, Zomato, Swiggy, and other platform-based workers.",
        "documents": [
            {
                "type": "platform_income_statement",
                "label": "Platform Income Statement",
                "description": "Upload your income or earnings statement downloaded directly from the gig platform app or portal (e.g., Ola driver app, Zomato partner portal).",
            },
        ],
    },
    "HOMEMAKER": {
        "employment_label": "Homemaker / No Income",
        "note": "A co-applicant with a valid income is mandatory. Upload the co-applicant's income proof and ID.",
        "documents": [
            {
                "type": "co_applicant_income_proof",
                "label": "Co-applicant Income Proof",
                "description": "Upload your co-applicant's latest salary slip, bank statement, or ITR as income proof.",
            },
            {
                "type": "co_applicant_id_proof",
                "label": "Co-applicant ID Proof",
                "description": "Upload a government-issued photo ID of the co-applicant (Aadhaar, PAN, Passport, or Voter ID).",
            },
        ],
    },
    "STUDENT_UNEMPLOYED": {
        "employment_label": "Unemployed / Student",
        "note": "A guarantor with income proof and a collateral document are required for this application.",
        "documents": [
            {
                "type": "guarantor_income_proof",
                "label": "Guarantor Income Proof",
                "description": "Upload the guarantor's latest salary slip, ITR, or bank statement as income verification.",
            },
            {
                "type": "collateral_document",
                "label": "Collateral Document",
                "description": "Upload a valid collateral document such as a property paper, Fixed Deposit certificate, or LIC policy.",
            },
        ],
    },
    "PENSIONER": {
        "employment_label": "Pensioner",
        "note": "Upload your latest pension slip and last 6 months' bank statement from your pension account.",
        "documents": [
            {
                "type": "pension_slip_latest",
                "label": "Pension Slip (Latest)",
                "description": "Upload your most recent pension disbursement slip from the pension authority or bank.",
            },
            {
                "type": "bank_statement_last_6_months",
                "label": "Bank Statement (Last 6 Months)",
                "description": "Upload your pension account bank statement for the last 6 months.",
            },
        ],
    },
    "NRI": {
        "employment_label": "NRI (Non-Resident Indian)",
        "note": "NRE account statement must be from an Indian bank's NRE account. Foreign income proof must be in English or translated.",
        "documents": [
            {
                "type": "foreign_income_proof",
                "label": "Foreign Income Proof",
                "description": "Upload your latest salary slip or employment contract from your overseas employer. Must be in English or officially translated.",
            },
            {
                "type": "nre_account_statement_last_6_months",
                "label": "NRE Account Statement (Last 6 Months)",
                "description": "Upload your NRE (Non-Resident External) account statement from an Indian bank for the last 6 months.",
            },
        ],
    },
}

ALLOWED_REGISTRATION_DOCUMENT_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
MAX_REGISTRATION_DOCUMENT_SIZE = 5 * 1024 * 1024
DOCUMENT_SLOT_FIELDS = (
    "employment_document_primary",
    "employment_document_secondary",
)


def get_required_document_definitions(employment_type):
    return EMPLOYMENT_DOCUMENT_REQUIREMENTS.get(employment_type, {}).get(
        "documents", []
    )


def build_employment_document_ui_config():
    return {
        employment_type: {
            "employment_label": config["employment_label"],
            "note": config.get("note", ""),
            "documents": config["documents"],
            "document_count": len(config["documents"]),
            "requires_co_applicant_details": employment_type == "HOMEMAKER",
            "requires_guarantor_details": employment_type == "STUDENT_UNEMPLOYED",
        }
        for employment_type, config in EMPLOYMENT_DOCUMENT_REQUIREMENTS.items()
    }


def validate_registration_document(uploaded_file):
    extension = (
        uploaded_file.name.rsplit(".", 1)[-1].lower()
        if "." in uploaded_file.name
        else ""
    )
    if extension not in ALLOWED_REGISTRATION_DOCUMENT_EXTENSIONS:
        raise forms.ValidationError("Only PDF, JPG, PNG files are accepted")
    if uploaded_file.size > MAX_REGISTRATION_DOCUMENT_SIZE:
        raise forms.ValidationError("File size must be under 5MB")
    return uploaded_file


class RegisterForm(forms.ModelForm):
    first_name = forms.CharField(max_length=100)
    last_name = forms.CharField(max_length=100)
    dob = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    gender = forms.ChoiceField(
        choices=[("", "Select")] + list(ApplicantProfile.GENDER_CHOICES)
    )
    marital_status = forms.ChoiceField(
        choices=[("", "Select")] + list(ApplicantProfile.MARITAL_STATUS_CHOICES)
    )
    mobile_number = forms.CharField(max_length=10)
    residential_address = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}))
    city = forms.CharField(max_length=100)
    state = forms.ChoiceField(
        choices=[("", "Select")] + list(ApplicantProfile.STATE_CHOICES)
    )
    pin_code = forms.CharField(max_length=6)

    employment_type = forms.ChoiceField(
        choices=[("", "Select")] + list(ApplicantProfile.EMPLOYMENT_TYPE_CHOICES)
    )
    employer_name = forms.CharField(max_length=255, required=False)
    salary_bank = forms.CharField(max_length=100, required=False)
    business_name = forms.CharField(max_length=255, required=False)
    years_in_business = forms.FloatField(required=False, min_value=0)
    monthly_salary = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    annual_income = forms.DecimalField(
        max_digits=15, decimal_places=2, required=False
    )
    average_monthly_income = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False
    )
    has_co_applicant = forms.BooleanField(required=False)
    co_applicant_name = forms.CharField(max_length=150, required=False)
    co_applicant_relationship = forms.CharField(max_length=100, required=False)
    co_applicant_income = forms.DecimalField(
        max_digits=15, decimal_places=2, required=False
    )
    guarantor_name = forms.CharField(max_length=150, required=False)
    guarantor_contact = forms.CharField(max_length=20, required=False)
    guarantor_income = forms.DecimalField(
        max_digits=15, decimal_places=2, required=False
    )
    employment_document_primary = forms.FileField(required=False)
    employment_document_secondary = forms.FileField(required=False)

    loan_amount_requested = forms.DecimalField(max_digits=12, decimal_places=2)
    loan_purpose = forms.ChoiceField(
        choices=[("", "Select")] + list(ApplicantProfile.LOAN_PURPOSE_CHOICES)
    )
    existing_emis = forms.DecimalField(max_digits=12, decimal_places=2)
    num_dependants = forms.IntegerField(min_value=0)

    has_residential_property = forms.BooleanField(required=False)
    has_commercial_property = forms.BooleanField(required=False)
    has_agricultural_land = forms.BooleanField(required=False)
    has_vehicle = forms.BooleanField(required=False)
    has_gold_jewellery = forms.BooleanField(required=False)
    has_fixed_deposits = forms.BooleanField(required=False)

    aadhaar_number = forms.CharField(max_length=12)
    pan_number = forms.CharField(max_length=10)

    password = forms.CharField(widget=forms.PasswordInput())
    confirm_password = forms.CharField(widget=forms.PasswordInput())

    class Meta:
        model = CustomUser
        fields = ["email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if not isinstance(
                field.widget,
                (forms.CheckboxInput, forms.RadioSelect, forms.HiddenInput),
            ):
                field.widget.attrs.update({"class": "form-control"})
            if isinstance(field, forms.ChoiceField):
                field.widget.attrs.update({"class": "form-select"})

        for name in DOCUMENT_SLOT_FIELDS:
            self.fields[name].widget.attrs.update(
                {
                    "class": "form-control d-none",
                    "accept": ".pdf,.png,.jpg,.jpeg",
                }
            )

        self.fields["co_applicant_name"].widget.attrs.update(
            {"placeholder": "Full name of co-applicant"}
        )
        self.fields["co_applicant_relationship"].widget.attrs.update(
            {"placeholder": "Relationship to co-applicant"}
        )
        self.fields["co_applicant_income"].widget.attrs.update(
            {"placeholder": "Monthly income"}
        )
        self.fields["guarantor_name"].widget.attrs.update(
            {"placeholder": "Full name of guarantor"}
        )
        self.fields["guarantor_contact"].widget.attrs.update(
            {"placeholder": "10-digit contact number"}
        )
        self.fields["guarantor_income"].widget.attrs.update(
            {"placeholder": "Monthly income"}
        )

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email and CustomUser.objects.filter(email=email).exists():
            raise forms.ValidationError("This email address is already registered.")
        return email

    def _required_document_definitions_for_request(self):
        employment_type = (
            self.cleaned_data.get("employment_type")
            or self.data.get("employment_type")
        )
        return get_required_document_definitions(employment_type)

    def _clean_document_slot(self, field_name):
        uploaded_file = self.cleaned_data.get(field_name)
        if not uploaded_file:
            return uploaded_file

        required_documents = self._required_document_definitions_for_request()
        try:
            slot_index = DOCUMENT_SLOT_FIELDS.index(field_name)
        except ValueError:
            return validate_registration_document(uploaded_file)

        if slot_index >= len(required_documents):
            return None
        return validate_registration_document(uploaded_file)

    def clean_employment_document_primary(self):
        return self._clean_document_slot("employment_document_primary")

    def clean_employment_document_secondary(self):
        return self._clean_document_slot("employment_document_secondary")

    def clean_guarantor_contact(self):
        contact = (self.cleaned_data.get("guarantor_contact") or "").strip()
        if contact and not re.match(r"^\d{10}$", contact):
            raise forms.ValidationError("Guarantor contact must be exactly 10 digits.")
        return contact

    def clean_first_name(self):
        name = self.cleaned_data.get("first_name", "").strip()
        if not name.isalpha():
            raise forms.ValidationError("First name must only contain letters.")
        return name

    def clean_last_name(self):
        name = self.cleaned_data.get("last_name", "").strip()
        if not name.isalpha():
            raise forms.ValidationError("Last name must only contain letters.")
        return name

    def clean_mobile_number(self):
        mobile = self.cleaned_data.get("mobile_number")
        if mobile and not re.match(r"^\d{10}$", mobile):
            raise forms.ValidationError("Mobile number must be exactly 10 digits.")
        return mobile

    def clean_pin_code(self):
        pin = self.cleaned_data.get("pin_code")
        if pin and not re.match(r"^\d{6}$", pin):
            raise forms.ValidationError("PIN code must be exactly 6 digits.")
        return pin

    def clean_aadhaar_number(self):
        aadhaar = self.cleaned_data.get("aadhaar_number")
        if aadhaar and not re.match(r"^\d{12}$", aadhaar):
            raise forms.ValidationError("Aadhaar number must be exactly 12 digits.")
        return aadhaar

    def clean_pan_number(self):
        pan = (self.cleaned_data.get("pan_number") or "").upper()
        if pan:
            if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", pan):
                raise forms.ValidationError("Invalid PAN format (e.g. ABCDE1234F).")
            if CustomUser.objects.filter(pan_number=pan).exists():
                raise forms.ValidationError(
                    "This PAN number is already registered with another account."
                )
        return pan

    def clean_dob(self):
        dob = self.cleaned_data.get("dob")
        if dob:
            from datetime import date

            today = date.today()
            age = today.year - dob.year - (
                (today.month, today.day) < (dob.month, dob.day)
            )
            if age < 18:
                raise forms.ValidationError(
                    "You must be at least 18 years old to apply."
                )
        return dob

    def clean(self):
        cleaned_data = super().clean()
        emp_type = cleaned_data.get("employment_type")
        loan_purpose = cleaned_data.get("loan_purpose")
        monthly_salary = cleaned_data.get("monthly_salary")
        annual_income = cleaned_data.get("annual_income")
        avg_income = cleaned_data.get("average_monthly_income")
        existing_emis = cleaned_data.get("existing_emis") or 0
        has_co_applicant = cleaned_data.get("has_co_applicant")
        co_applicant_income = cleaned_data.get("co_applicant_income")
        guarantor_income = cleaned_data.get("guarantor_income")

        risk_flag = "LOW"
        income_variability_high = False
        effective_monthly_income = 0

        if emp_type in ["SALARIED_GOVT", "SALARIED_PRIVATE"]:
            if not cleaned_data.get("employer_name"):
                self.add_error("employer_name", "Employer name is required.")
            if not monthly_salary:
                self.add_error("monthly_salary", "Monthly salary is required.")
            effective_monthly_income = float(monthly_salary or 0)

        elif emp_type in ["SELF_EMPLOYED_PROFESSIONAL", "SELF_EMPLOYED_BUSINESS"]:
            if not annual_income:
                self.add_error("annual_income", "Annual income is required.")
            if not cleaned_data.get("years_in_business"):
                self.add_error("years_in_business", "Years in business is required.")
            effective_monthly_income = float(annual_income or 0) / 12

        elif emp_type in ["DAILY_WAGE", "SEASONAL", "GIG_WORKER", "FARMER"]:
            if not avg_income:
                self.add_error(
                    "average_monthly_income",
                    "Average monthly income is required.",
                )
            effective_monthly_income = float(avg_income or 0)
            income_variability_high = True
            risk_flag = "MEDIUM"

        elif emp_type == "PENSIONER":
            if not avg_income:
                self.add_error("average_monthly_income", "Pension amount is required.")
            effective_monthly_income = float(avg_income or 0)

        elif emp_type == "NRI":
            if not avg_income:
                self.add_error(
                    "average_monthly_income",
                    "Average monthly income is required for NRI registrations.",
                )
            effective_monthly_income = float(avg_income or 0)

        elif emp_type == "HOMEMAKER":
            if not has_co_applicant:
                self.add_error(
                    "has_co_applicant",
                    "A co-applicant is mandatory for homemaker registrations.",
                )
            if not cleaned_data.get("co_applicant_name"):
                self.add_error("co_applicant_name", "Co-applicant name is required.")
            if not cleaned_data.get("co_applicant_relationship"):
                self.add_error(
                    "co_applicant_relationship",
                    "Co-applicant relationship is required.",
                )
            if not co_applicant_income:
                self.add_error(
                    "co_applicant_income",
                    "Co-applicant income is required.",
                )
            effective_monthly_income = float(co_applicant_income or 0)

        elif emp_type == "STUDENT_UNEMPLOYED":
            if not cleaned_data.get("guarantor_name"):
                self.add_error("guarantor_name", "Guarantor name is required.")
            if not cleaned_data.get("guarantor_contact"):
                self.add_error(
                    "guarantor_contact",
                    "Guarantor contact is required.",
                )
            if not guarantor_income:
                self.add_error(
                    "guarantor_income",
                    "Guarantor income is required.",
                )
            effective_monthly_income = float(guarantor_income or 0)

        required_documents = get_required_document_definitions(emp_type)
        missing_document_fields = []
        for index, field_name in enumerate(DOCUMENT_SLOT_FIELDS):
            required_document = (
                required_documents[index] if index < len(required_documents) else None
            )
            uploaded_file = cleaned_data.get(field_name)
            raw_uploaded_file = self.files.get(field_name)
            if required_document and not uploaded_file and not raw_uploaded_file:
                missing_document_fields.append(required_document["type"])
                self.add_error(
                    field_name,
                    f"Upload {required_document['label']} to continue.",
                )
        cleaned_data["missing_document_fields"] = missing_document_fields

        if loan_purpose == "BUSINESS" and emp_type not in [
            "SELF_EMPLOYED_PROFESSIONAL",
            "SELF_EMPLOYED_BUSINESS",
        ]:
            self.add_error(
                "loan_purpose",
                "Business loans require a self-employed business owner profile.",
            )

        income_required = 15000 if loan_purpose != "EDUCATION" else 10000
        if loan_purpose != "MEDICAL" and effective_monthly_income < income_required:
            income_error_field = "average_monthly_income"
            if emp_type in ["SALARIED_GOVT", "SALARIED_PRIVATE"]:
                income_error_field = "monthly_salary"
            elif emp_type in ["SELF_EMPLOYED_PROFESSIONAL", "SELF_EMPLOYED_BUSINESS"]:
                income_error_field = "annual_income"
            elif emp_type == "HOMEMAKER":
                income_error_field = "co_applicant_income"
            elif emp_type == "STUDENT_UNEMPLOYED":
                income_error_field = "guarantor_income"
            self.add_error(
                income_error_field,
                f"Minimum income of INR {income_required} required for {loan_purpose} loans.",
            )

        if effective_monthly_income > 0:
            dti = float(existing_emis) / effective_monthly_income
            cleaned_data["dti_ratio"] = dti
            if dti > 0.5:
                risk_flag = "REJECTED"
                self.add_error(
                    "existing_emis",
                    f"Rejected: DTI ratio {dti:.2f} exceeds 0.5 threshold.",
                )
            elif dti >= 0.3:
                risk_flag = "HIGH" if risk_flag == "MEDIUM" else "MEDIUM"
        else:
            cleaned_data["dti_ratio"] = 0

        if income_variability_high and risk_flag != "REJECTED":
            risk_flag = "HIGH"

        cleaned_data["risk_flag"] = risk_flag
        cleaned_data["income_variability_high"] = income_variability_high

        if cleaned_data.get("password") != cleaned_data.get("confirm_password"):
            self.add_error("confirm_password", "Passwords do not match.")

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.phone_number = self.cleaned_data["mobile_number"]
        user.pan_number = self.cleaned_data["pan_number"]
        user.role = "USER"
        user.set_password(self.cleaned_data["password"])

        if commit:
            user.save()
            from datetime import date

            applicant_profile = ApplicantProfile.objects.create(
                user=user,
                dob=self.cleaned_data["dob"],
                gender=self.cleaned_data["gender"],
                marital_status=self.cleaned_data["marital_status"],
                residential_address=self.cleaned_data["residential_address"],
                city=self.cleaned_data["city"],
                state=self.cleaned_data["state"],
                pin_code=self.cleaned_data["pin_code"],
                employment_type=self.cleaned_data["employment_type"],
                employer_business_name=self.cleaned_data.get("employer_name")
                or self.cleaned_data.get("business_name"),
                salary_bank=self.cleaned_data.get("salary_bank"),
                years_in_business=self.cleaned_data.get("years_in_business"),
                monthly_income=(
                    self.cleaned_data.get("monthly_salary")
                    or self.cleaned_data.get("average_monthly_income")
                    or self.cleaned_data.get("co_applicant_income")
                    or self.cleaned_data.get("guarantor_income")
                ),
                annual_income=self.cleaned_data.get("annual_income"),
                income_variability_high=self.cleaned_data["income_variability_high"],
                employment_document_primary=self.cleaned_data.get(
                    "employment_document_primary"
                ),
                employment_document_secondary=self.cleaned_data.get(
                    "employment_document_secondary"
                ),
                co_applicant_name=self.cleaned_data.get("co_applicant_name"),
                co_applicant_relationship=self.cleaned_data.get(
                    "co_applicant_relationship"
                ),
                co_applicant_income=self.cleaned_data.get("co_applicant_income"),
                guarantor_name=self.cleaned_data.get("guarantor_name"),
                guarantor_contact=self.cleaned_data.get("guarantor_contact"),
                guarantor_income=self.cleaned_data.get("guarantor_income"),
                loan_amount_requested=self.cleaned_data["loan_amount_requested"],
                loan_purpose=self.cleaned_data["loan_purpose"],
                existing_emis=self.cleaned_data["existing_emis"],
                num_dependants=self.cleaned_data["num_dependants"],
                has_co_applicant=self.cleaned_data["has_co_applicant"],
                has_residential_property=self.cleaned_data[
                    "has_residential_property"
                ],
                has_commercial_property=self.cleaned_data["has_commercial_property"],
                has_agricultural_land=self.cleaned_data["has_agricultural_land"],
                has_vehicle=self.cleaned_data["has_vehicle"],
                has_gold_jewellery=self.cleaned_data["has_gold_jewellery"],
                has_fixed_deposits=self.cleaned_data["has_fixed_deposits"],
                aadhaar_number=self.cleaned_data["aadhaar_number"],
                pan_number=self.cleaned_data["pan_number"],
                dti_ratio=self.cleaned_data["dti_ratio"],
                risk_flag=self.cleaned_data["risk_flag"],
            )

            required_documents = get_required_document_definitions(
                self.cleaned_data["employment_type"]
            )
            for index, document_definition in enumerate(required_documents):
                uploaded_file = self.cleaned_data.get(DOCUMENT_SLOT_FIELDS[index])
                if not uploaded_file:
                    continue
                ApplicantEmploymentDocument.objects.create(
                    applicant_profile=applicant_profile,
                    user=user,
                    employment_type=self.cleaned_data["employment_type"],
                    document_type=document_definition["type"],
                    file=uploaded_file,
                    file_name=uploaded_file.name,
                    file_path="",
                )

            from users.models import FinancialProfile

            age = (date.today() - self.cleaned_data["dob"]).days // 365
            income = float(
                self.cleaned_data.get("monthly_salary")
                or self.cleaned_data.get("average_monthly_income")
                or self.cleaned_data.get("co_applicant_income")
                or self.cleaned_data.get("guarantor_income")
                or 0
            ) * 12
            if not income:
                income = float(self.cleaned_data.get("annual_income") or 0)
            primary_document_name = (
                applicant_profile.employment_document_primary.name
                if applicant_profile.employment_document_primary
                else None
            )

            FinancialProfile.objects.create(
                user=user,
                person_age=age,
                person_income=income,
                person_home_ownership=(
                    "OWN" if self.cleaned_data["has_residential_property"] else "RENT"
                ),
                person_emp_length=self.cleaned_data.get("years_in_business") or 1.0,
                cb_person_cred_hist_length=1,
                cb_person_default_on_file="N",
                salary_slip=primary_document_name,
                income_proof_status=(
                    "PENDING" if primary_document_name else "NOT_SUBMITTED"
                ),
                income_proof_uploaded_at=(
                    timezone.now() if primary_document_name else None
                ),
            )
        return user


class LoginForm(forms.Form):
    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "name@company.com",
                "autocomplete": "email",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your password",
                "autocomplete": "current-password",
            }
        ),
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("password")

        if email and password:
            self.user_cache = authenticate(
                self.request,
                username=email,
                password=password,
            )
            if self.user_cache is None:
                fallback_username = (
                    CustomUser.objects.filter(email=email)
                    .values_list("username", flat=True)
                    .first()
                    or email
                )
                self.user_cache = authenticate(
                    self.request,
                    username=fallback_username,
                    password=password,
                )

            if self.user_cache is None:
                raise forms.ValidationError("Invalid email or password.")

            if not self.user_cache.is_active:
                raise forms.ValidationError(
                    "This account is inactive. Please contact support."
                )

        return cleaned_data

    def get_user(self):
        return self.user_cache
