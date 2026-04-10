from django import forms

from .models import SystemAnnouncement
from bank_officer.models import BankOfficerProfile


class SystemAnnouncementForm(forms.ModelForm):
    class Meta:
        model = SystemAnnouncement
        fields = ["title", "message", "audience", "is_active"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs.setdefault("class", css_class)
        self.fields["is_active"].widget.attrs.update({"class": "form-check-input"})


from users.models import CustomUser


class OfficerCreationForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)
    organization_name = forms.CharField(max_length=150)
    employee_id = forms.CharField(max_length=32)
    branch_name = forms.CharField(max_length=100)

    class Meta:
        model = CustomUser
        fields = ["email", "first_name", "last_name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_email(self):
        email = self.cleaned_data.get("email", "").lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("password") != cleaned_data.get("confirm_password"):
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email
        user.role = "BANK_OFFICER"
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
            BankOfficerProfile.objects.create(
                user=user,
                organization_name=self.cleaned_data["organization_name"],
                employee_id=self.cleaned_data["employee_id"],
                branch_name=self.cleaned_data["branch_name"],
            )
        return user


class OfficerManagementForm(forms.ModelForm):
    is_active = forms.BooleanField(required=False)

    class Meta:
        model = BankOfficerProfile
        fields = ["organization_name", "employee_id", "branch_name", "approval_limit"]
        widgets = {
            "approval_limit": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        self.fields["is_active"].widget.attrs.update({"class": "form-check-input"})
        if self.instance and self.instance.pk:
            self.fields["is_active"].initial = self.instance.user.is_active

    def save(self, commit=True):
        profile = super().save(commit=False)
        if commit:
            profile.save()
            profile.user.is_active = self.cleaned_data["is_active"]
            profile.user.save(update_fields=["is_active"])
        return profile
