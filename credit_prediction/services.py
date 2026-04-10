from __future__ import annotations

from functools import lru_cache

from django.db import transaction
from django.utils import timezone

from ml_engine.fraud_detection.service import get_fraud_detection_service
from ml_engine.prediction_model.service import get_credit_risk_engine
from ml_engine.prediction_model.train import clean_training_frame, load_dataset
from recommendations.services import RecommendationService
from users.models import FinancialProfile

from .models import CreditPrediction, LoanApplication


LOAN_GRADE_RATE_BANDS = (
    (9.02, "A"),
    (12.09, "B"),
    (14.32, "C"),
    (15.95, "D"),
    (17.57, "E"),
    (19.27, "F"),
)


def derive_loan_grade(loan_int_rate):
    # Keep applicant input minimal by inferring the grade from the interest-rate bands
    # represented in the training dataset.
    try:
        interest_rate = float(loan_int_rate)
    except (TypeError, ValueError):
        return "C"

    for upper_bound, grade in LOAN_GRADE_RATE_BANDS:
        if interest_rate <= upper_bound:
            return grade
    return "G"


@lru_cache(maxsize=1)
def get_loan_ratio_reference():
    dataset = clean_training_frame(load_dataset())
    return {
        "overall": float(dataset["loan_percent_income"].median()),
        "by_intent": {
            key: float(value)
            for key, value in dataset.groupby("loan_intent")["loan_percent_income"].median().items()
        },
        "by_intent_grade": {
            (intent, grade): float(value)
            for (intent, grade), value in dataset.groupby(
                ["loan_intent", "loan_grade"]
            )["loan_percent_income"].median().items()
        },
        "by_intent_home": {
            (intent, home): float(value)
            for (intent, home), value in dataset.groupby(
                ["loan_intent", "person_home_ownership"]
            )["loan_percent_income"].median().items()
        },
    }


def derive_loan_percent_income(profile, application_data: dict):
    # DIRECT CALCULATION (Prioritize actual values)
    amount = application_data.get("loan_amnt")
    income = getattr(profile, "person_income", None)
    if amount and income and float(income) > 0:
        return round(min(1.0, max(0.01, float(amount) / float(income))), 2)

    # MEDIAN-BASED SUGGESTION (Fallback)
    reference = get_loan_ratio_reference()
    intent = application_data.get("loan_intent")
    grade = application_data.get("loan_grade") or derive_loan_grade(
        application_data.get("loan_int_rate")
    )
    home_ownership = getattr(profile, "person_home_ownership", None)

    ratio = reference["by_intent_grade"].get(
        (intent, grade),
        reference["by_intent"].get(intent, reference["overall"]),
    )
    intent_median = reference["by_intent"].get(intent)
    intent_home_median = reference["by_intent_home"].get((intent, home_ownership))
    if intent_median is not None and intent_home_median is not None:
        ratio += intent_home_median - intent_median

    return round(min(1.0, max(0.01, ratio)), 2)


def derive_loan_amount(person_income, loan_percent_income):
    try:
        annual_income = float(person_income)
        income_ratio = float(loan_percent_income)
    except (TypeError, ValueError):
        return 0.0
    return round(annual_income * income_ratio, 2)


@transaction.atomic
def create_prediction_workflow(user, profile_data: dict, application_data: dict):
    profile, _ = FinancialProfile.objects.update_or_create(
        user=user,
        defaults=profile_data,
    )
    application_defaults = dict(application_data)
    if not application_defaults.get("loan_grade"):
        application_defaults["loan_grade"] = derive_loan_grade(
            application_defaults.get("loan_int_rate")
        )
    if application_defaults.get("loan_percent_income") in (None, ""):
        application_defaults["loan_percent_income"] = derive_loan_percent_income(
            profile,
            application_defaults,
        )
    if application_defaults.get("loan_amnt") in (None, ""):
        application_defaults["loan_amnt"] = derive_loan_amount(
            profile.person_income,
            application_defaults.get("loan_percent_income"),
        )
    application = LoanApplication.objects.create(user=user, **application_defaults)

    feature_payload = {
        **profile.to_feature_payload(),
        "loan_intent": application.loan_intent,
        "loan_grade": application.loan_grade,
        "loan_amnt": application.loan_amnt,
        "loan_int_rate": application.loan_int_rate,
        "loan_percent_income": application.loan_percent_income,
    }

    result = get_credit_risk_engine().predict(feature_payload)

    prediction = CreditPrediction.objects.create(
        application=application,
        risk_probability=result["risk_probability"],
        credit_score=result["credit_score"],
        risk_category=result["risk_category"],
        shap_explanations=result["shap_explanations"],
        lime_explanations=result["lime_explanations"],
        feature_payload=result["feature_payload"],
        model_name=result["model_name"],
        model_version=result["model_version"],
    )

    # AUTOMATED DECISION LOGIC: Dynamic Tiering via RiskConfiguration
    from admin_panel.models import RiskConfiguration
    config = RiskConfiguration.get_solo()
    
    risk_prob = result["risk_probability"]
    
    if not config.auto_decision_enabled:
        application.status = "PENDING"
        application.decision_notes = "Manual Review Required: Automated AI decisioning is currently disabled by system administrator."
    elif risk_prob < config.approval_threshold:
        application.status = "APPROVED"
        application.decision_notes = f"Automated AI Approval: Low-risk footprint detect (< {config.approval_threshold})."
    elif config.approval_threshold <= risk_prob <= config.rejection_threshold:
        application.status = "PENDING"
        application.decision_notes = f"AI Review Required: Medium-risk factors ({config.approval_threshold}-{config.rejection_threshold}) detected. Routed for manual oversight."
    else:
        application.status = "REJECTED"
        application.decision_notes = f"Automated AI Rejection: High-risk probability (> {config.rejection_threshold}) detected with significant default signals."
    
    application.reviewed_at = timezone.now()
    application.save(update_fields=["status", "decision_notes", "reviewed_at"])

    RecommendationService().generate(user, profile, application, prediction)
    get_fraud_detection_service().evaluate(user, profile, application, prediction)
    return application, prediction


@transaction.atomic
def review_application(application, officer, decision: str, notes: str = ""):
    application.status = decision
    application.reviewed_by = officer
    application.decision_notes = notes
    application.reviewed_at = timezone.now()
    application.save(update_fields=["status", "reviewed_by", "decision_notes", "reviewed_at"])
    return application
