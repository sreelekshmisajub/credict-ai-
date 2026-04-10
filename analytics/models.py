from django.db import models


class ModelMetricSnapshot(models.Model):
    model_name = models.CharField(max_length=120)
    model_version = models.CharField(max_length=40, default="v1")
    dataset_rows = models.PositiveIntegerField(default=0)
    accuracy = models.FloatField(default=0)
    precision = models.FloatField(default=0)
    recall = models.FloatField(default=0)
    f1_score = models.FloatField(default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.model_name} {self.model_version}"
