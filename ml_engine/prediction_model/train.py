"""Training utilities for the CreditSense AI prediction engine."""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = Path(__file__).resolve().parent
DATASET_PATH = PROJECT_ROOT / "dataset" / "credit_risk_dataset.csv"

FEATURE_COLUMNS = [
    "person_income",
    "cb_person_cred_hist_length",
    "cb_person_default_on_file",
    "loan_amnt",
    "loan_percent_income",
    "person_age",
    "person_emp_length",
    "loan_int_rate",
    "person_home_ownership",
    "loan_intent",
    "loan_grade",
]
CATEGORICAL_COLUMNS = [
    "person_home_ownership",
    "loan_intent",
    "loan_grade",
    "cb_person_default_on_file",
]
TARGET_COLUMN = "loan_status"
MODEL_VERSION = "2026.03.14"


def load_dataset(path: Path = DATASET_PATH) -> pd.DataFrame:
    return pd.read_csv(path)


def clean_training_frame(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.dropna(subset=["person_emp_length", "loan_int_rate"]).copy()
    return cleaned.reset_index(drop=True)


def encode_categorical_columns(
    df: pd.DataFrame,
    label_encoders: dict[str, LabelEncoder] | None = None,
    fit: bool = False,
) -> tuple[pd.DataFrame, dict[str, LabelEncoder]]:
    transformed = df.copy()
    encoders = label_encoders or {}
    for column in CATEGORICAL_COLUMNS:
        if fit:
            encoder = LabelEncoder()
            transformed[column] = encoder.fit_transform(transformed[column].astype(str))
            encoders[column] = encoder
        else:
            encoder = encoders[column]
            mapping = {label: idx for idx, label in enumerate(encoder.classes_)}
            unknown_values = set(transformed[column].astype(str)) - set(mapping)
            if unknown_values:
                raise ValueError(
                    f"Unexpected category for {column}: {', '.join(sorted(unknown_values))}"
                )
            transformed[column] = transformed[column].astype(str).map(mapping)
    return transformed, encoders


def _dataset_profile(df: pd.DataFrame) -> dict:
    return {
        "row_count": int(len(df)),
        "loan_amount_q95": float(df["loan_amnt"].quantile(0.95)),
        "loan_percent_income_q95": float(df["loan_percent_income"].quantile(0.95)),
        "interest_rate_q95": float(df["loan_int_rate"].quantile(0.95)),
        "median_income": float(df["person_income"].median()),
        "median_credit_history": float(df["cb_person_cred_hist_length"].median()),
        "median_employment_length": float(df["person_emp_length"].median()),
    }


def train_and_save_artifacts() -> dict:
    df = clean_training_frame(load_dataset())
    encoded_df, label_encoders = encode_categorical_columns(df, fit=True)

    X = encoded_df[FEATURE_COLUMNS]
    y = encoded_df[TARGET_COLUMN]
    class_distribution = {
        str(key): int(value) for key, value in y.value_counts().sort_index().to_dict().items()
    }

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    rf_model = RandomForestClassifier(
        n_estimators=250,
        random_state=42,
        max_depth=12,
        min_samples_leaf=3,
    )
    rf_model.fit(X_train, y_train)

    lr_model = LogisticRegression(random_state=42, max_iter=1000)
    lr_model.fit(X_train, y_train)

    rf_predictions = rf_model.predict(X_test)
    lr_predictions = lr_model.predict(X_test)

    metadata = {
        "model_name": "CreditSense Ensemble",
        "model_version": MODEL_VERSION,
        "dataset_path": str(DATASET_PATH),
        "dataset_profile": _dataset_profile(df),
        "feature_columns": FEATURE_COLUMNS,
        "categorical_columns": CATEGORICAL_COLUMNS,
        "class_distribution": class_distribution,
        "feature_importance": {
            feature: float(importance)
            for feature, importance in zip(FEATURE_COLUMNS, rf_model.feature_importances_)
        },
        "metrics": {
            "random_forest": {
                "accuracy": float(accuracy_score(y_test, rf_predictions)),
                "report": classification_report(y_test, rf_predictions, output_dict=True),
            },
            "logistic_regression": {
                "accuracy": float(accuracy_score(y_test, lr_predictions)),
                "report": classification_report(y_test, lr_predictions, output_dict=True),
            },
        },
    }

    with (ARTIFACT_DIR / "rf_model.pkl").open("wb") as file_obj:
        pickle.dump(rf_model, file_obj)
    with (ARTIFACT_DIR / "lr_model.pkl").open("wb") as file_obj:
        pickle.dump(lr_model, file_obj)
    with (ARTIFACT_DIR / "scaler.pkl").open("wb") as file_obj:
        pickle.dump(scaler, file_obj)
    with (ARTIFACT_DIR / "label_encoders.pkl").open("wb") as file_obj:
        pickle.dump(label_encoders, file_obj)
    with (ARTIFACT_DIR / "feature_names.pkl").open("wb") as file_obj:
        pickle.dump(FEATURE_COLUMNS, file_obj)
    with (ARTIFACT_DIR / "model_metadata.json").open("w", encoding="utf-8") as file_obj:
        json.dump(metadata, file_obj, indent=2)

    return metadata


if __name__ == "__main__":
    details = train_and_save_artifacts()
    rf_accuracy = details["metrics"]["random_forest"]["accuracy"]
    lr_accuracy = details["metrics"]["logistic_regression"]["accuracy"]
    print(f"Random Forest Accuracy: {rf_accuracy:.4f}")
    print(f"Logistic Regression Accuracy: {lr_accuracy:.4f}")
