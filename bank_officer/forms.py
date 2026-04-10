from django import forms

from authentication.validators import validate_real_email, validate_real_name
from users.models import CustomUser

from .models import BankOfficerProfile


class OfficerDecisionForm(forms.Form):
    DECISION_CHOICES = (
        ("APPROVED", "Approve loan"),
        ("REJECTED", "Reject loan"),
        ("VERIFICATION_REQUIRED", "Request additional verification"),
    )

    decision = forms.ChoiceField(choices=DECISION_CHOICES)
    decision_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 5}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["decision"].widget.attrs.update({"class": "form-select"})
        self.fields["decision_notes"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "Add context for the underwriting decision or follow-up request.",
            }
        )

    def clean(self):
        cleaned_data = super().clean()
        decision = cleaned_data.get("decision")
        notes = (cleaned_data.get("decision_notes") or "").strip()
        if decision == "VERIFICATION_REQUIRED" and not notes:
            self.add_error(
                "decision_notes",
                "Please explain what requires additional verification.",
            )
        return cleaned_data


class IncomeProofReviewForm(forms.Form):
    INCOME_PROOF_CHOICES = (
        ("PENDING", "Pending Review"),
        ("VERIFIED", "Verified"),
        ("REJECTED", "Rejected"),
    )

    income_proof_status = forms.ChoiceField(choices=INCOME_PROOF_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["income_proof_status"].widget.attrs.update({"class": "form-select"})


class OfficerAccountForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ["first_name", "last_name", "email"]

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
                "placeholder": "Work email",
                "autocomplete": "email",
                "inputmode": "email",
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
            user.save(update_fields=["first_name", "last_name", "email", "username"])
        return user


class BankOfficerProfileForm(forms.ModelForm):
    class Meta:
        model = BankOfficerProfile
        fields = ["organization_name", "employee_id", "branch_name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["organization_name"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "Bank, NBFC, or financial company",
            }
        )
        self.fields["employee_id"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "Official employee ID (optional)",
            }
        )
        self.fields["employee_id"].required = False
        self.fields["branch_name"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "Branch, city, or operations unit",
            }
        )
        self.fields["branch_name"].required = False

    def clean_organization_name(self):
        return validate_real_name(
            self.cleaned_data["organization_name"],
            "Bank or financial company",
        )

    def clean_employee_id(self):
        employee_id = (self.cleaned_data["employee_id"] or "").strip()
        if not employee_id:
            return None
        queryset = BankOfficerProfile.objects.exclude(pk=self.instance.pk)
        if queryset.filter(employee_id__iexact=employee_id).exists():
            raise forms.ValidationError("This employee ID is already in use.")
        return employee_id

    def clean_branch_name(self):
        branch_name = (self.cleaned_data["branch_name"] or "").strip()
        if not branch_name:
            return ""
        return validate_real_name(branch_name, "Branch name")
