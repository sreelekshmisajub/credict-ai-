from django.db import models
from users.models import CustomUser


class LoanApplication(models.Model):
    LOAN_INTENT_CHOICES = (
        ("PERSONAL", "Personal"),
        ("EDUCATION", "Education"),
        ("MEDICAL", "Medical"),
        ("VENTURE", "Venture"),
        ("HOMEIMPROVEMENT", "Home Improvement"),
        ("DEBTCONSOLIDATION", "Debt Consolidation"),
    )
    LOAN_GRADE_CHOICES = tuple((grade, grade) for grade in "ABCDEFG")
    STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("VERIFICATION_REQUIRED", "Verification Required"),
    )

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="loan_applications",
    )
    loan_intent = models.CharField(
        max_length=50,
        choices=LOAN_INTENT_CHOICES,
        help_text="Purpose of the loan",
    )
    loan_grade = models.CharField(
        max_length=5,
        choices=LOAN_GRADE_CHOICES,
        help_text="Assigned loan grade",
    )
    loan_amnt = models.FloatField(help_text="Requested loan amount")
    loan_int_rate = models.FloatField(help_text="Applied interest rate")
    loan_percent_income = models.FloatField(
        help_text="Loan amount as a percentage of annual income"
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default="PENDING")
    is_flagged_by_officer = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_loans",
        limit_choices_to={"role": "BANK_OFFICER"},
    )
    decision_notes = models.TextField(blank=True, default="")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Loan {self.id} - {self.user.username} - {self.status}"


class CreditPrediction(models.Model):
    application = models.OneToOneField(
        LoanApplication,
        on_delete=models.CASCADE,
        related_name="prediction",
    )
    risk_probability = models.FloatField(help_text="Float precision of default probability")
    credit_score = models.IntegerField(help_text="Translated 300-850 Credit Score")
    risk_category = models.CharField(max_length=20, help_text="Low Risk, Medium Risk, High Risk")
    shap_explanations = models.JSONField(default=dict)
    lime_explanations = models.JSONField(default=dict, blank=True)
    feature_payload = models.JSONField(default=dict, blank=True)
    model_name = models.CharField(max_length=120, default="CreditSense Ensemble")
    model_version = models.CharField(max_length=40, default="v1")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Prediction for Loan {self.application.id} - {self.risk_category}"


class FraudAlert(models.Model):
    ALERT_TYPE_LABEL_ALIASES = {
        "Unusual transactions": "High liability exposure",
    }

    SEVERITY_CHOICES = (
        ("LOW", "Low"),
        ("MEDIUM", "Medium"),
        ("HIGH", "High"),
        ("CRITICAL", "Critical"),
    )

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="fraud_alerts",
    )
    application = models.ForeignKey(
        LoanApplication,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="associated_alerts",
    )
    alert_type = models.CharField(
        max_length=100,
        help_text="E.g., Abnormal spending behavior, Multiple applications",
    )
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES,
        help_text="Low, Medium, High, Critical",
    )
    description = models.TextField()
    recommended_action = models.CharField(max_length=255, blank=True, default="")
    resolved = models.BooleanField(default=False)
    detected_at = models.DateTimeField(auto_now_add=True)

    @property
    def display_alert_type(self):
        return self.ALERT_TYPE_LABEL_ALIASES.get(self.alert_type, self.alert_type)

    def __str__(self):
        return f"ALERT [{self.severity}]: {self.user.username} - {self.display_alert_type}"
