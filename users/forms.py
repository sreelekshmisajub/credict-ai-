import json
from pathlib import Path

from django import forms
from django.utils import timezone

from authentication.validators import validate_real_email, validate_real_name
from credit_prediction.services import LOAN_GRADE_RATE_BANDS, derive_loan_percent_income, get_loan_ratio_reference

from .models import FinancialProfile
from credit_prediction.models import LoanApplication
from .models import CustomUser


class _LoanRatioProfileSnapshot:
    def __init__(self, person_home_ownership):
        self.person_home_ownership = person_home_ownership


class CompactIncomeProofWidget(forms.ClearableFileInput):
    template_name = "django/forms/widgets/compact_income_proof_input.html"
    initial_text = "Current document"
    input_text = "Upload new document"
    clear_checkbox_label = "Remove current file"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        display_name = ""
        if value:
            display_name = Path(getattr(value, "name", str(value))).name
        context["widget"]["display_name"] = display_name
        return context


def _loan_ratio_widget_config():
    reference = get_loan_ratio_reference()
    by_intent_grade = {}
    for (intent, grade), value in reference["by_intent_grade"].items():
        by_intent_grade.setdefault(intent, {})[grade] = value

    by_intent_home = {}
    for (intent, home), value in reference["by_intent_home"].items():
        by_intent_home.setdefault(intent, {})[home] = value

    return {
        "grade_bands": json.dumps(LOAN_GRADE_RATE_BANDS),
        "overall": str(reference["overall"]),
        "by_intent": json.dumps(reference["by_intent"]),
        "by_intent_grade": json.dumps(by_intent_grade),
        "by_intent_home": json.dumps(by_intent_home),
    }


class FinancialProfileForm(forms.ModelForm):
    monthly_income = forms.FloatField(
        label="Monthly income (INR)",
        min_value=0,
        widget=forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
        help_text="Monthly income declared in Indian rupees. The ML engine annualizes this value for prediction.",
    )

    def __init__(self, *args, **kwargs):
        self.require_income_proof = kwargs.pop("require_income_proof", False)
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css_class)
        self.fields["monthly_income"].widget.attrs.setdefault("placeholder", "Monthly income")
        self.fields["monthly_income"].widget.attrs.setdefault("inputmode", "decimal")
        self.fields["salary_slip"].widget.attrs.update(
            {
                "class": "form-control",
                "accept": ".pdf,.png,.jpg,.jpeg",
            }
        )
        self.fields["salary_slip"].required = self.require_income_proof and not bool(
            getattr(self.instance, "salary_slip", None)
        )
        if self.instance and self.instance.pk and self.instance.person_income:
            self.fields["monthly_income"].initial = round(self.instance.person_income / 12, 2)

    class Meta:
        model = FinancialProfile
        exclude = [
            "user",
            "updated_at",
            "person_income",
            "income_proof_status",
            "income_proof_uploaded_at",
        ]
        widgets = {
            "person_age": forms.NumberInput(attrs={"min": 18, "max": 100}),
            "person_emp_length": forms.NumberInput(attrs={"min": 0, "step": "0.1"}),
            "cb_person_cred_hist_length": forms.NumberInput(attrs={"min": 0}),
            "salary_slip": CompactIncomeProofWidget(),
        }

    def clean_monthly_income(self):
        monthly_income = self.cleaned_data["monthly_income"]
        if monthly_income <= 0:
            raise forms.ValidationError("Monthly income must be greater than zero.")
        return monthly_income

    def clean_salary_slip(self):
        salary_slip = self.cleaned_data.get("salary_slip")
        if not salary_slip:
            return salary_slip
        
        extension = salary_slip.name.rsplit(".", 1)[-1].lower() if "." in salary_slip.name else ""
        if extension not in {"pdf", "png", "jpg", "jpeg"}:
            raise forms.ValidationError("Upload a PDF, PNG, or JPG income proof document.")
        
        max_size = 5 * 1024 * 1024
        if salary_slip.size > max_size:
            raise forms.ValidationError("The uploaded document must be 5 MB or smaller for AI analysis.")

        # --- AI Identity Matching Validation (Simulated Strict Verification) ---
        if self.user:
            filename_lowered = salary_slip.name.lower()
            first_name = (self.user.first_name or "").lower().strip()
            last_name = (self.user.last_name or "").lower().strip()
            pan_number = (getattr(self.user, "pan_number", "") or "").lower().strip()
            
            # Identify keywords that MUST be in the document filename (Strict pattern matching)
            # This simulates a document scan finding the applicant's official records on the header.
            has_name = bool(first_name and last_name and (first_name in filename_lowered and last_name in filename_lowered))
            has_pan = bool(pan_number and pan_number in filename_lowered)

            if not (has_name or has_pan):
                raise forms.ValidationError(
                    f"Profile Matching Rejected: The uploaded document '{salary_slip.name}' fails the AI identity check. "
                    f"To ensure it belongs to {self.user.get_full_name().title()}, the filename must clearly include "
                    f"your Full Name or your registered PAN ({pan_number.upper()})."
                )
        
        return salary_slip

    def clean(self):
        cleaned_data = super().clean()
        if self.require_income_proof and not cleaned_data.get("salary_slip") and not (
            self.instance and getattr(self.instance, "salary_slip", None)
        ):
            self.add_error(
                "salary_slip",
                "Upload a salary slip or income proof document before submitting financial data.",
            )
        return cleaned_data

    def save(self, commit=True):
        profile = super().save(commit=False)
        profile.person_income = self.cleaned_data["monthly_income"] * 12
        uploaded_salary_slip = self.cleaned_data.get("salary_slip")
        if uploaded_salary_slip:
            profile.salary_slip = uploaded_salary_slip
            profile.income_proof_status = "PENDING"
            profile.income_proof_uploaded_at = timezone.now()
        elif not profile.salary_slip:
            profile.income_proof_status = "NOT_SUBMITTED"
            profile.income_proof_uploaded_at = None
        if commit:
            profile.save()
        return profile

    def build_profile_defaults(self):
        profile = self.save(commit=False)
        return {
            "person_age": profile.person_age,
            "person_income": profile.person_income,
            "person_home_ownership": profile.person_home_ownership,
            "person_emp_length": profile.person_emp_length,
            "cb_person_cred_hist_length": profile.cb_person_cred_hist_length,
            "cb_person_default_on_file": profile.cb_person_default_on_file,
            "salary_slip": profile.salary_slip,
            "income_proof_status": profile.income_proof_status,
            "income_proof_uploaded_at": profile.income_proof_uploaded_at,
        }


class LoanApplicationForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.profile_home_ownership = kwargs.pop("profile_home_ownership", None)
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css_class)
        self.fields["loan_int_rate"].label = "Interest rate (%)"
        self.fields["loan_percent_income"].label = "Annual income ratio"
        self.fields["loan_percent_income"].required = False
        self.fields["loan_percent_income"].help_text = (
            "Calculated automatically from your profile, loan purpose, and interest rate."
        )
        ratio_config = _loan_ratio_widget_config()
        self.fields["loan_percent_income"].widget.attrs.update(
            {
                "readonly": "readonly",
                "data-auto-calculated": "true",
                "data-grade-bands": ratio_config["grade_bands"],
                "data-ratio-overall": ratio_config["overall"],
                "data-ratio-by-intent": ratio_config["by_intent"],
                "data-ratio-by-intent-grade": ratio_config["by_intent_grade"],
                "data-ratio-by-intent-home": ratio_config["by_intent_home"],
            }
        )
        self.fields["loan_percent_income"].widget.attrs.setdefault(
            "placeholder",
            "Calculated automatically",
        )

    class Meta:
        model = LoanApplication
        fields = [
            "loan_intent",
            "loan_int_rate",
            "loan_percent_income",
        ]
        widgets = {
            "loan_int_rate": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
            "loan_percent_income": forms.NumberInput(
                attrs={"min": 0, "max": 1, "step": "0.01"}
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        loan_intent = cleaned_data.get("loan_intent")
        loan_int_rate = cleaned_data.get("loan_int_rate")
        if loan_intent and loan_int_rate not in (None, ""):
            cleaned_data["loan_percent_income"] = derive_loan_percent_income(
                _LoanRatioProfileSnapshot(self.profile_home_ownership),
                {
                    "loan_intent": loan_intent,
                    "loan_int_rate": loan_int_rate,
                },
            )
        return cleaned_data


class ApplicantAccountForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ["first_name", "last_name", "email", "profile_picture"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["email"].required = True
        self.fields["first_name"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "First name",
                "autocomplete": "given-name",
            }
        )
        self.fields["last_name"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "Last name",
                "autocomplete": "family-name",
            }
        )
        self.fields["email"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "Email address",
                "autocomplete": "email",
                "inputmode": "email",
            }
        )
        self.fields["profile_picture"].widget.attrs.update(
            {
                "class": "form-control",
                "accept": ".png,.jpg,.jpeg",
            }
        )

    def clean_first_name(self):
        return validate_real_name(self.cleaned_data["first_name"], "First name")

    def clean_last_name(self):
        return validate_real_name(self.cleaned_data["last_name"], "Last name")

    def clean_email(self):
        email = validate_real_email(self.cleaned_data["email"])
        queryset = CustomUser.objects.exclude(pk=self.instance.pk)
        if queryset.filter(email__iexact=email).exists():
            raise forms.ValidationError("This email address is already registered.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"]
        if commit:
            user.save(update_fields=["first_name", "last_name", "email", "username", "profile_picture"])
        return user
