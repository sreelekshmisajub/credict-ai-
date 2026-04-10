from __future__ import annotations

FEATURE_LABELS = {
    "person_income": "Income",
    "cb_person_cred_hist_length": "Credit history",
    "cb_person_default_on_file": "Repayment behavior",
    "loan_amnt": "Outstanding liabilities",
    "loan_percent_income": "Credit utilization",
    "person_age": "Applicant age",
    "person_emp_length": "Employment length",
    "loan_int_rate": "Interest rate",
    "person_home_ownership": "Home ownership",
    "loan_intent": "Loan intent",
    "loan_grade": "Loan grade",
}


def _format_points(value: float, max_abs_value: float) -> str:
    if max_abs_value == 0:
        return "+0.0"
    points = 40 * value / max_abs_value
    return f"{points:+.1f}"


def format_shap_explanations(feature_names, shap_values, top_n: int = 5) -> dict:
    ranked = sorted(
        zip(feature_names, shap_values),
        key=lambda item: abs(item[1]),
        reverse=True,
    )[:top_n]
    max_abs_value = max((abs(value) for _, value in ranked), default=0)
    return {
        FEATURE_LABELS.get(name, name): _format_points(value, max_abs_value)
        for name, value in ranked
    }


def format_lime_explanations(explanation_pairs, top_n: int = 5) -> dict:
    formatted = {}
    for statement, weight in explanation_pairs[:top_n]:
        human_statement = statement
        for field_name, label in FEATURE_LABELS.items():
            human_statement = human_statement.replace(field_name, label)
        formatted[human_statement] = f"{weight:+.3f}"
    return formatted


def format_feature_payload(feature_payload: dict) -> dict:
    return {
        FEATURE_LABELS.get(key, key): value for key, value in feature_payload.items()
    }
