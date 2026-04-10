from __future__ import annotations

import json
import logging
import os
import pickle
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from lime.lime_tabular import LimeTabularExplainer

from ml_engine.explainable_ai.service import (
    format_feature_payload,
    format_lime_explanations,
    format_shap_explanations,
)
from .train import (
    ARTIFACT_DIR,
    CATEGORICAL_COLUMNS,
    FEATURE_COLUMNS,
    clean_training_frame,
    encode_categorical_columns,
    load_dataset,
    train_and_save_artifacts,
)

logger = logging.getLogger(__name__)

ARTIFACT_FILENAMES = (
    "rf_model.pkl",
    "lr_model.pkl",
    "scaler.pkl",
    "label_encoders.pkl",
    "feature_names.pkl",
)

RECOVERABLE_ARTIFACT_ERRORS = (
    ModuleNotFoundError,
    ImportError,
    AttributeError,
    EOFError,
    pickle.UnpicklingError,
)


class EnsembleWrapper:
    def __init__(self, rf_model, lr_model):
        self.rf_model = rf_model
        self.lr_model = lr_model

    def predict_proba(self, X):
        rf_probs = self.rf_model.predict_proba(X)
        lr_probs = self.lr_model.predict_proba(X)
        return (rf_probs + lr_probs) / 2


class CreditRiskEngine:
    def __init__(self):
        self._load_runtime_artifacts()
        self.ensemble = EnsembleWrapper(self.rf_model, self.lr_model)
        self._reference_scaled = self._build_reference_frame()
        self.tree_explainer = self._build_tree_explainer()
        self.lime_explainer = LimeTabularExplainer(
            training_data=self._reference_scaled,
            feature_names=self.feature_names,
            class_names=["No Default", "Default"],
            mode="classification",
        )

    def _ensure_artifacts(self):
        required_artifacts = [ARTIFACT_DIR / name for name in ARTIFACT_FILENAMES]
        required_artifacts.append(ARTIFACT_DIR / "model_metadata.json")
        if any(not artifact.exists() for artifact in required_artifacts):
            train_and_save_artifacts()

    def _load_runtime_artifacts(self):
        self._ensure_artifacts()
        try:
            self._assign_loaded_artifacts()
        except RECOVERABLE_ARTIFACT_ERRORS as exc:
            logger.warning(
                "Model artifacts are incompatible with the current environment. "
                "Rebuilding prediction artifacts from the dataset. Root cause: %s",
                exc,
            )
            train_and_save_artifacts()
            self._assign_loaded_artifacts()

    def _assign_loaded_artifacts(self):
        self.rf_model = self._load_pickle("rf_model.pkl")
        self.lr_model = self._load_pickle("lr_model.pkl")
        self.scaler = self._load_pickle("scaler.pkl")
        self.label_encoders = self._load_pickle("label_encoders.pkl")
        self.feature_names = self._load_pickle("feature_names.pkl")
        self.metadata = self._load_metadata()

    def _load_pickle(self, filename):
        with (ARTIFACT_DIR / filename).open("rb") as file_obj:
            return pickle.load(file_obj)

    def _load_metadata(self) -> dict:
        with (ARTIFACT_DIR / "model_metadata.json").open("r", encoding="utf-8") as file_obj:
            return json.load(file_obj)

    def _build_tree_explainer(self):
        try:
            os.environ.setdefault("NUMBA_DISABLE_COVERAGE", "1")
            import shap

            return shap.TreeExplainer(self.rf_model)
        except Exception:
            return None

    def _encode_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        encoded = frame.copy()
        for column in CATEGORICAL_COLUMNS:
            encoder = self.label_encoders[column]
            mapping = {label: idx for idx, label in enumerate(encoder.classes_)}
            unknown_values = set(encoded[column].astype(str)) - set(mapping)
            if unknown_values:
                raise ValueError(
                    f"Unexpected category for {column}: {', '.join(sorted(unknown_values))}"
                )
            encoded[column] = encoded[column].astype(str).map(mapping)
        return encoded

    def _build_reference_frame(self):
        reference_df = clean_training_frame(load_dataset())
        encoded_df, _ = encode_categorical_columns(
            reference_df,
            label_encoders=self.label_encoders,
            fit=False,
        )
        return self.scaler.transform(encoded_df[FEATURE_COLUMNS])

    def _risk_category(self, probability: float) -> str:
        if probability < 0.34:
            return "Low Risk"
        if probability < 0.67:
            return "Medium Risk"
        return "High Risk"

    def _credit_score(self, probability: float) -> int:
        score = round(850 - (probability * 550))
        return max(300, min(850, score))

    def _extract_positive_class_shap(self, scaled_features):
        if self.tree_explainer is None:
            importances = np.asarray(self.rf_model.feature_importances_)
            return scaled_features * importances

        shap_values = self.tree_explainer.shap_values(scaled_features)
        if isinstance(shap_values, list):
            return np.asarray(shap_values[1])
        shap_array = np.asarray(shap_values)
        if shap_array.ndim == 3:
            return shap_array[:, :, 1]
        return shap_array

    def predict(self, feature_payload: dict) -> dict:
        feature_frame = pd.DataFrame([feature_payload], columns=FEATURE_COLUMNS)
        encoded_frame = self._encode_frame(feature_frame)
        scaled_features = self.scaler.transform(encoded_frame[FEATURE_COLUMNS])

        probability = float(self.ensemble.predict_proba(scaled_features)[0, 1])
        shap_values = self._extract_positive_class_shap(scaled_features)[0]

        lime_explanation = self.lime_explainer.explain_instance(
            scaled_features[0],
            self.ensemble.predict_proba,
            num_features=min(6, len(FEATURE_COLUMNS)),
        )

        return {
            "risk_probability": round(probability, 4),
            "credit_score": self._credit_score(probability),
            "risk_category": self._risk_category(probability),
            "shap_explanations": format_shap_explanations(
                self.feature_names,
                shap_values,
            ),
            "lime_explanations": format_lime_explanations(lime_explanation.as_list()),
            "feature_payload": format_feature_payload(feature_payload),
            "model_name": self.metadata["model_name"],
            "model_version": self.metadata["model_version"],
        }


@lru_cache(maxsize=1)
def get_credit_risk_engine() -> CreditRiskEngine:
    return CreditRiskEngine()
