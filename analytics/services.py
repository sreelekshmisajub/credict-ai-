from __future__ import annotations

import json
from pathlib import Path

from django.db.models import Avg, Count

from credit_prediction.models import CreditPrediction, FraudAlert, LoanApplication
from ml_engine.explainable_ai.service import FEATURE_LABELS
from users.models import CustomUser

from .models import ModelMetricSnapshot

METADATA_PATH = (
    Path(__file__).resolve().parent.parent
    / "ml_engine"
    / "prediction_model"
    / "model_metadata.json"
)


def load_model_metadata():
    if not METADATA_PATH.exists():
        return {}

    with METADATA_PATH.open("r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def sync_latest_model_snapshot():
    metadata = load_model_metadata()
    if not metadata:
        return None

    rf_metrics = metadata["metrics"]["random_forest"]
    report = rf_metrics["report"]["weighted avg"]
    snapshot, _ = ModelMetricSnapshot.objects.update_or_create(
        model_name=metadata["model_name"],
        model_version=metadata["model_version"],
        defaults={
            "dataset_rows": metadata["dataset_profile"]["row_count"],
            "accuracy": rf_metrics["accuracy"],
            "precision": report["precision"],
            "recall": report["recall"],
            "f1_score": report["f1-score"],
            "notes": "Random Forest metrics shown for monitoring; final runtime score uses RF/LR ensemble averaging.",
        },
    )
    return snapshot


def build_system_analytics():
    snapshot = sync_latest_model_snapshot()
    metadata = load_model_metadata()
    dataset_profile = metadata.get("dataset_profile", {})
    feature_importance = metadata.get("feature_importance", {})
    class_distribution = metadata.get("class_distribution", {})
    total_training_rows = dataset_profile.get("row_count", 0)
    positive_class_rows = class_distribution.get("1", 0)
    default_rate = (
        (positive_class_rows / total_training_rows) * 100 if total_training_rows else 0
    )
    raw_preview_features = [
        (
            FEATURE_LABELS.get(feature_name, feature_name),
            round(importance * 100, 1),
        )
        for feature_name, importance in sorted(
            feature_importance.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:5]
    ]
    preview_feature_max = max(
        [value for _, value in raw_preview_features],
        default=1,
    )
    preview_features = [
        {
            "label": label,
            "value": value,
            "width": round((value / preview_feature_max) * 100, 1) if preview_feature_max else 0,
        }
        for label, value in raw_preview_features
    ]
    rf_metrics = metadata.get("metrics", {}).get("random_forest", {})
    lr_metrics = metadata.get("metrics", {}).get("logistic_regression", {})
    risk_breakdown = {
        row["risk_category"]: row["total"]
        for row in CreditPrediction.objects.values("risk_category").annotate(total=Count("id"))
    }
    application_breakdown = {
        row["status"]: row["total"]
        for row in LoanApplication.objects.values("status").annotate(total=Count("id"))
    }
    application_volume_series = []
    from django.utils import timezone
    from datetime import timedelta
    today = timezone.now().date()
    for i in range(7):
        day = today - timedelta(days=i)
        count = LoanApplication.objects.filter(created_at__date=day).count()
        application_volume_series.append({"label": day.strftime("%b %d"), "count": count})
    application_volume_series.reverse()

    approved_count = application_breakdown.get("APPROVED", 0)
    rejected_count = application_breakdown.get("REJECTED", 0)
    total_decided = approved_count + rejected_count
    approval_ratio = (approved_count / total_decided * 100) if total_decided else 0
    rejection_ratio = (rejected_count / total_decided * 100) if total_decided else 0

    return {
        "users": CustomUser.objects.count(),
        "applicants": CustomUser.objects.filter(role="USER").count(),
        "bank_officers": CustomUser.objects.filter(role="BANK_OFFICER").count(),
        "admins": CustomUser.objects.filter(role="ADMIN").count(),
        "applications": LoanApplication.objects.count(),
        "predictions": CreditPrediction.objects.count(),
        "open_fraud_alerts": FraudAlert.objects.filter(resolved=False).count(),
        "average_credit_score": CreditPrediction.objects.aggregate(
            score=Avg("credit_score")
        )["score"]
        or 0,
        "dataset_rows": snapshot.dataset_rows if snapshot else 0,
        "model_name": metadata.get("model_name", ""),
        "model_version": metadata.get("model_version", ""),
        "model_accuracy_percent": rf_metrics.get("accuracy", 0) * 100,
        "baseline_accuracy_percent": lr_metrics.get("accuracy", 0) * 100,
        "default_rate_percent": round(default_rate, 1),
        "median_income": dataset_profile.get("median_income", 0),
        "median_credit_history": dataset_profile.get("median_credit_history", 0),
        "median_employment_length": dataset_profile.get("median_employment_length", 0),
        "loan_amount_q95": dataset_profile.get("loan_amount_q95", 0),
        "loan_percent_income_q95": dataset_profile.get("loan_percent_income_q95", 0),
        "interest_rate_q95": dataset_profile.get("interest_rate_q95", 0),
        "preview_features": preview_features,
        "preview_feature_max": preview_feature_max,
        "risk_breakdown": risk_breakdown,
        "application_breakdown": application_breakdown,
        "application_volume_series": application_volume_series,
        "approval_ratio": round(approval_ratio, 1),
        "rejection_ratio": round(rejection_ratio, 1),
        "latest_snapshot": ModelMetricSnapshot.objects.first(),
    }
