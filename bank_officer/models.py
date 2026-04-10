from django.db import models
from users.models import CustomUser


class BankOfficerProfile(models.Model):
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="bank_officer_profile",
        limit_choices_to={"role": "BANK_OFFICER"},
    )
    organization_name = models.CharField(max_length=150)
    employee_id = models.CharField(max_length=32, unique=True, blank=True, null=True)
    branch_name = models.CharField(max_length=100, blank=True, default="")
    approval_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        primary_label = self.employee_id or self.organization_name
        return f"{primary_label} - {self.user.username}"
