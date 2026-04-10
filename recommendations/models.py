from django.db import models
from credit_prediction.models import CreditPrediction
from users.models import CustomUser


class CreditRecommendation(models.Model):
    CATEGORY_CHOICES = (
        ("DEBT", "Debt"),
        ("PAYMENT", "Payment"),
        ("HISTORY", "History"),
        ("STABILITY", "Stability"),
        ("GENERAL", "General"),
    )

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="credit_recommendations",
    )
    prediction = models.ForeignKey(
        CreditPrediction,
        on_delete=models.CASCADE,
        related_name="recommendations",
    )
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default="GENERAL")
    message = models.TextField()
    priority = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["priority", "-created_at"]

    def __str__(self):
        return f"Recommendation for {self.user.username} ({self.category})"
