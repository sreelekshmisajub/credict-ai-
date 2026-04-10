from __future__ import annotations

from ml_engine.prediction_model.train import clean_training_frame, load_dataset

from .models import CreditRecommendation


class RecommendationService:
    def __init__(self):
        dataset = clean_training_frame(load_dataset())
        self.median_income = float(dataset["person_income"].median())
        self.median_credit_history = float(dataset["cb_person_cred_hist_length"].median())
        self.median_employment_length = float(dataset["person_emp_length"].median())

    def generate(self, user, profile, application, prediction):
        CreditRecommendation.objects.filter(prediction=prediction).delete()
        messages = []

        if application.loan_percent_income > 0.35:
            messages.append(
                (
                    "DEBT",
                    "Reduce outstanding debt or request a smaller loan so your debt-to-income pressure stays lower.",
                    1,
                )
            )
        if profile.cb_person_default_on_file == "Y":
            messages.append(
                (
                    "PAYMENT",
                    "Maintain on-time repayments consistently; recent defaults are strongly increasing your risk profile.",
                    1,
                )
            )
        if profile.cb_person_cred_hist_length < self.median_credit_history:
            messages.append(
                (
                    "HISTORY",
                    "A longer credit history would strengthen future applications, so keep older accounts healthy and active.",
                    2,
                )
            )
        if profile.person_emp_length < self.median_employment_length:
            messages.append(
                (
                    "STABILITY",
                    "Income stability matters. A longer continuous employment record can improve the next score refresh.",
                    2,
                )
            )
        if prediction.risk_category == "High Risk":
            messages.append(
                (
                    "GENERAL",
                    "Focus on lowering borrowing exposure first, then re-apply once your affordability indicators improve.",
                    1,
                )
            )
        if not messages:
            messages.append(
                (
                    "GENERAL",
                    "Your current profile looks stable. Keep utilization moderate and payments punctual to preserve this score.",
                    3,
                )
            )

        recommendations = [
            CreditRecommendation.objects.create(
                user=user,
                prediction=prediction,
                category=category,
                message=message,
                priority=priority,
            )
            for category, message, priority in messages
        ]
        return recommendations
