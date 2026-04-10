from __future__ import annotations

from datetime import timedelta
from functools import lru_cache

from django.utils import timezone

from credit_prediction.models import FraudAlert
from ml_engine.prediction_model.train import clean_training_frame, load_dataset


class FraudDetectionService:
    def __init__(self):
        dataset = clean_training_frame(load_dataset())
        self.loan_amount_q95 = float(dataset["loan_amnt"].quantile(0.95))
        self.loan_percent_income_q95 = float(dataset["loan_percent_income"].quantile(0.95))
        self.interest_rate_q95 = float(dataset["loan_int_rate"].quantile(0.95))

    def evaluate(self, user, profile, application, prediction):
        FraudAlert.objects.filter(application=application).delete()
        created_alerts = []

        recent_application_count = user.loan_applications.filter(
            created_at__gte=timezone.now() - timedelta(days=7)
        ).exclude(pk=application.pk).count()

        if recent_application_count >= 2:
            created_alerts.append(
                FraudAlert.objects.create(
                    user=user,
                    application=application,
                    alert_type="Multiple loan applications",
                    severity="HIGH",
                    description=(
                        "The applicant submitted several loan requests within a short "
                        "time window, which may indicate credit shopping or stress."
                    ),
                    recommended_action="Review application history before approval.",
                )
            )

        if (
            application.loan_amnt >= self.loan_amount_q95
            and application.loan_percent_income >= self.loan_percent_income_q95
        ):
            created_alerts.append(
                FraudAlert.objects.create(
                    user=user,
                    application=application,
                    alert_type="High liability exposure",
                    severity="CRITICAL",
                    description=(
                        "Requested liability exposure is an outlier versus the real "
                        "training dataset and the applicant's income profile."
                    ),
                    recommended_action="Request supporting documents and manual review.",
                )
            )

        if (
            application.loan_percent_income >= self.loan_percent_income_q95
            or application.loan_int_rate >= self.interest_rate_q95
            or prediction.risk_probability >= 0.8
        ):
            created_alerts.append(
                FraudAlert.objects.create(
                    user=user,
                    application=application,
                    alert_type="Abnormal spending behavior",
                    severity="MEDIUM",
                    description=(
                        "The new application suggests unusually high borrowing pressure "
                        "relative to typical applicants in the dataset."
                    ),
                    recommended_action="Verify affordability and recent liabilities.",
                )
            )

        if profile.cb_person_default_on_file == "Y" and prediction.risk_probability >= 0.65:
            created_alerts.append(
                FraudAlert.objects.create(
                    user=user,
                    application=application,
                    alert_type="High repayment anomaly",
                    severity="HIGH",
                    description=(
                        "Past default history combined with the current risk estimate "
                        "suggests elevated repayment anomalies."
                    ),
                    recommended_action="Escalate to senior officer review.",
                )
            )

        return created_alerts


@lru_cache(maxsize=1)
def get_fraud_detection_service():
    return FraudDetectionService()
