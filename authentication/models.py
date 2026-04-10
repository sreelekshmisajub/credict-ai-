from django.db import models
from users.models import CustomUser


class LoginAudit(models.Model):
    user = models.ForeignKey(
        CustomUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="login_audits",
    )
    username_attempt = models.CharField(max_length=150)
    successful = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        status = "SUCCESS" if self.successful else "FAILED"
        return f"{status} login for {self.username_attempt}"
