from django.db import models
from users.models import CustomUser


class AdminProfile(models.Model):
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="admin_profile",
        limit_choices_to={"role": "ADMIN"},
    )
    department = models.CharField(max_length=100, default="Risk Operations")
    can_manage_models = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Admin {self.user.username}"


class SystemAnnouncement(models.Model):
    AUDIENCE_CHOICES = (
        ("ALL", "All users"),
        ("BANK_OFFICER", "Bank officers"),
        ("USER", "Applicants"),
        ("ADMIN", "Administrators"),
    )

    title = models.CharField(max_length=160)
    message = models.TextField()
    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default="ALL")
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcements_created",
        limit_choices_to={"role": "ADMIN"},
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class AdminActionLog(models.Model):
    ACTION_CHOICES = (
        ("USER_ACCESS", "User access update"),
        ("OFFICER_ACCESS", "Bank officer management"),
        ("FRAUD_REVIEW", "Fraud monitoring action"),
        ("ANNOUNCEMENT", "System announcement"),
        ("RISK_CONFIG", "Risk rules update"),
    )

    actor = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admin_actions",
        limit_choices_to={"role": "ADMIN"},
    )
    action_type = models.CharField(max_length=32, choices=ACTION_CHOICES)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_action_type_display()} by {self.actor or 'Unknown admin'}"


class RiskConfiguration(models.Model):
    """
    Centralized control for the CreditSense AI Auto-Decision Engine.
    """
    auto_decision_enabled = models.BooleanField(default=True, help_text="Global toggle for AI-based auto-approval/rejection.")
    approval_threshold = models.FloatField(default=0.30, help_text="Applications with risk < this value are auto-approved.")
    rejection_threshold = models.FloatField(default=0.60, help_text="Applications with risk > this value are auto-rejected.")
    
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "Risk Configuration"
        verbose_name_plural = "Risk Configurations"

    def __str__(self):
        return f"Risk Config (Approved < {self.approval_threshold}, Rejected > {self.rejection_threshold})"

    @classmethod
    def get_solo(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj
