from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from pathlib import Path


def salary_slip_upload_path(instance, filename):
    extension = Path(filename).suffix.lower() or ".bin"
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    user_id = instance.user_id or "new"
    return f"income_proofs/user_{user_id}/salary_slip_{timestamp}{extension}"


def applicant_primary_document_upload_path(instance, filename):
    extension = Path(filename).suffix.lower() or ".bin"
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    user_id = instance.user_id or "new"
    return (
        f"registration_docs/user_{user_id}/employment_primary_{timestamp}{extension}"
    )


def applicant_secondary_document_upload_path(instance, filename):
    extension = Path(filename).suffix.lower() or ".bin"
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    user_id = instance.user_id or "new"
    return (
        f"registration_docs/user_{user_id}/employment_secondary_{timestamp}{extension}"
    )


def applicant_employment_document_upload_path(instance, filename):
    extension = Path(filename).suffix.lower() or ".bin"
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
    user_id = instance.user_id or "new"
    document_type = instance.document_type or "document"
    return (
        f"registration_docs/user_{user_id}/{document_type}_{timestamp}{extension}"
    )


class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ("USER", "User"),
        ("BANK_OFFICER", "Bank Officer"),
        ("ADMIN", "Admin"),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="USER")
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    pan_number = models.CharField(max_length=10, blank=True, null=True, unique=True)
    is_verified = models.BooleanField(default=False)
    profile_picture = models.ImageField(upload_to="profile_pics/", blank=True, null=True)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_applicant(self):
        return self.role == "USER"

    @property
    def is_bank_officer(self):
        return self.role == "BANK_OFFICER"

    @property
    def is_platform_admin(self):
        return self.role == "ADMIN"


class ApplicantProfile(models.Model):
    GENDER_CHOICES = (
        ("MALE", "Male"),
        ("FEMALE", "Female"),
        ("OTHER", "Other"),
    )
    MARITAL_STATUS_CHOICES = (
        ("SINGLE", "Single"),
        ("MARRIED", "Married"),
        ("DIVORCED", "Divorced"),
        ("WIDOWED", "Widowed"),
    )
    EMPLOYMENT_TYPE_CHOICES = (
        ("SALARIED_GOVT", "Salaried (Govt/PSU)"),
        ("SALARIED_PRIVATE", "Salaried (Private)"),
        ("SELF_EMPLOYED_PROFESSIONAL", "Self-Employed Professional"),
        ("SELF_EMPLOYED_BUSINESS", "Self-Employed Business"),
        ("DAILY_WAGE", "Daily Wage Worker"),
        ("FARMER", "Agricultural / Farmer"),
        ("SEASONAL", "Seasonal Worker"),
        ("GIG_WORKER", "Gig Worker"),
        ("HOMEMAKER", "Homemaker / No Income"),
        ("STUDENT_UNEMPLOYED", "Unemployed / Student"),
        ("PENSIONER", "Pensioner"),
        ("NRI", "NRI (Non-Resident Indian)"),
    )
    LOAN_PURPOSE_CHOICES = (
        ("HOME", "Home Purchase / Renovation"),
        ("VEHICLE", "Vehicle Purchase"),
        ("BUSINESS", "Business Expansion"),
        ("EDUCATION", "Education Loan"),
        ("MEDICAL", "Medical Emergency"),
        ("DEBT", "Debt Consolidation"),
        ("CONSUMER", "Consumer Goods"),
        ("AGRICULTURE", "Agriculture / Crop Loan"),
        ("PERSONAL", "Personal Use (Other)"),
    )
    RISK_FLAG_CHOICES = (
        ("LOW", "Low Risk"),
        ("MEDIUM", "Medium Risk"),
        ("HIGH", "High Risk"),
        ("REJECTED", "Rejected"),
    )
    STATE_CHOICES = (
        ("AP", "Andhra Pradesh"), ("AR", "Arunachal Pradesh"), ("AS", "Assam"),
        ("BR", "Bihar"), ("CT", "Chhattisgarh"), ("GA", "Goa"), ("GJ", "Gujarat"),
        ("HR", "Haryana"), ("HP", "Himachal Pradesh"), ("JK", "Jammu and Kashmir"),
        ("JH", "Jharkhand"), ("KA", "Karnataka"), ("KL", "Kerala"), ("MP", "Madhya Pradesh"),
        ("MH", "Maharashtra"), ("MN", "Manipur"), ("ML", "Meghalaya"), ("MZ", "Mizoram"),
        ("NL", "Nagaland"), ("OR", "Odisha"), ("PB", "Punjab"), ("RJ", "Rajasthan"),
        ("SK", "Sikkim"), ("TN", "Tamil Nadu"), ("TG", "Telangana"), ("TR", "Tripura"),
        ("UP", "Uttar Pradesh"), ("UT", "Uttarakhand"), ("WB", "West Bengal"),
        ("AN", "Andaman and Nicobar Islands"), ("CH", "Chandigarh"), ("DN", "Dadra and Nagar Haveli"),
        ("DD", "Daman and Diu"), ("DL", "Delhi"), ("LD", "Lakshadweep"), ("PY", "Puducherry"),
    )

    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="applicant_profile",
    )
    dob = models.DateField()
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    marital_status = models.CharField(max_length=20, choices=MARITAL_STATUS_CHOICES)
    residential_address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2, choices=STATE_CHOICES)
    pin_code = models.CharField(max_length=6)
    
    employment_type = models.CharField(max_length=50, choices=EMPLOYMENT_TYPE_CHOICES)
    employer_business_name = models.CharField(max_length=255, blank=True, null=True)
    salary_bank = models.CharField(max_length=100, blank=True, null=True)
    years_in_business = models.FloatField(null=True, blank=True)
    monthly_income = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    annual_income = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    income_variability_high = models.BooleanField(default=False)
    employment_document_primary = models.FileField(
        upload_to=applicant_primary_document_upload_path,
        blank=True,
        null=True,
    )
    employment_document_secondary = models.FileField(
        upload_to=applicant_secondary_document_upload_path,
        blank=True,
        null=True,
    )
    co_applicant_name = models.CharField(max_length=150, blank=True, null=True)
    co_applicant_relationship = models.CharField(max_length=100, blank=True, null=True)
    co_applicant_income = models.DecimalField(
        max_digits=15, decimal_places=2, blank=True, null=True
    )
    guarantor_name = models.CharField(max_length=150, blank=True, null=True)
    guarantor_contact = models.CharField(max_length=20, blank=True, null=True)
    guarantor_income = models.DecimalField(
        max_digits=15, decimal_places=2, blank=True, null=True
    )
    
    loan_amount_requested = models.DecimalField(max_digits=12, decimal_places=2)
    loan_purpose = models.CharField(max_length=100, choices=LOAN_PURPOSE_CHOICES)
    existing_emis = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    num_dependants = models.IntegerField(default=0)
    has_co_applicant = models.BooleanField(default=False)
    
    # Assets represented as flags
    has_residential_property = models.BooleanField(default=False)
    has_commercial_property = models.BooleanField(default=False)
    has_agricultural_land = models.BooleanField(default=False)
    has_vehicle = models.BooleanField(default=False)
    has_gold_jewellery = models.BooleanField(default=False)
    has_fixed_deposits = models.BooleanField(default=False)
    
    aadhaar_number = models.CharField(max_length=12)
    pan_number = models.CharField(max_length=10)
    
    dti_ratio = models.FloatField(null=True, blank=True)
    risk_flag = models.CharField(max_length=20, choices=RISK_FLAG_CHOICES, default="LOW")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Applicant Profile - {self.user.email} [{self.risk_flag}]"


class ApplicantEmploymentDocument(models.Model):
    VALIDATION_STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("VERIFIED", "Verified"),
        ("REJECTED", "Rejected"),
    )

    applicant_profile = models.ForeignKey(
        ApplicantProfile,
        on_delete=models.CASCADE,
        related_name="employment_documents",
    )
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="employment_documents",
    )
    employment_type = models.CharField(
        max_length=50, choices=ApplicantProfile.EMPLOYMENT_TYPE_CHOICES
    )
    document_type = models.CharField(max_length=100)
    file = models.FileField(upload_to=applicant_employment_document_upload_path)
    file_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    validation_status = models.CharField(
        max_length=20, choices=VALIDATION_STATUS_CHOICES, default="PENDING"
    )

    class Meta:
        unique_together = ("applicant_profile", "document_type")
        ordering = ["uploaded_at"]

    def save(self, *args, **kwargs):
        if self.file:
            self.file_name = Path(self.file.name).name
            self.file_path = self.file.name
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.email} - {self.document_type}"


class FinancialProfile(models.Model):
    HOME_OWNERSHIP_CHOICES = (
        ("RENT", "Rent"),
        ("OWN", "Own"),
        ("MORTGAGE", "Mortgage"),
        ("OTHER", "Other"),
    )

    DEFAULT_HISTORY_CHOICES = (("Y", "Yes"), ("N", "No"))
    INCOME_PROOF_STATUS_CHOICES = (
        ("NOT_SUBMITTED", "Not Submitted"),
        ("PENDING", "Pending Review"),
        ("VERIFIED", "Verified"),
        ("REJECTED", "Rejected"),
    )

    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="financial_profile",
    )
    person_age = models.IntegerField(help_text="Age of the applicant")
    person_income = models.FloatField(help_text="Annual income of the applicant")
    person_home_ownership = models.CharField(
        max_length=20,
        choices=HOME_OWNERSHIP_CHOICES,
        help_text="e.g. RENT, OWN, MORTGAGE",
    )
    person_emp_length = models.FloatField(help_text="Employment length in years")
    cb_person_cred_hist_length = models.IntegerField(
        help_text="Credit history length in years"
    )
    cb_person_default_on_file = models.CharField(
        max_length=1,
        choices=DEFAULT_HISTORY_CHOICES,
        help_text="Historical default Y/N",
    )
    salary_slip = models.FileField(
        upload_to=salary_slip_upload_path,
        blank=True,
        null=True,
        help_text="Salary slip or income proof document uploaded by the applicant",
    )
    income_proof_status = models.CharField(
        max_length=20,
        choices=INCOME_PROOF_STATUS_CHOICES,
        default="NOT_SUBMITTED",
    )
    income_proof_uploaded_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __str__(self):
        return f"Financial Profile - {self.user.username}"

    @property
    def repayment_behavior(self):
        return "Needs Improvement" if self.cb_person_default_on_file == "Y" else "Stable"

    @property
    def monthly_income_estimate(self):
        return round(self.person_income / 12, 2) if self.person_income else 0

    @property
    def income_proof_filename(self):
        if not self.salary_slip:
            return ""
        return Path(self.salary_slip.name).name

    def to_feature_payload(self):
        return {
            "person_age": self.person_age,
            "person_income": self.person_income,
            "person_home_ownership": self.person_home_ownership,
            "person_emp_length": self.person_emp_length,
            "cb_person_cred_hist_length": self.cb_person_cred_hist_length,
            "cb_person_default_on_file": self.cb_person_default_on_file,
        }
