from unittest.mock import MagicMock, patch

from django.test import TestCase

from ml_engine.prediction_model.service import CreditRiskEngine
from recommendations.models import CreditRecommendation
from users.models import CustomUser

from .models import CreditPrediction
from .services import create_prediction_workflow


class PredictionWorkflowTests(TestCase):
    def test_prediction_workflow_creates_full_outputs(self):
        user = CustomUser.objects.create_user(
            username="riskuser",
            password="StrongPass123",
            role="USER",
        )

        application, prediction = create_prediction_workflow(
            user,
            {
                "person_age": 31,
                "person_income": 62000,
                "person_home_ownership": "RENT",
                "person_emp_length": 6.0,
                "cb_person_cred_hist_length": 7,
                "cb_person_default_on_file": "N",
            },
            {
                "loan_intent": "PERSONAL",
                "loan_int_rate": 12.1,
            },
        )

        self.assertEqual(CreditPrediction.objects.count(), 1)
        self.assertEqual(prediction.application, application)
        self.assertEqual(application.loan_percent_income, 0.17)
        self.assertEqual(application.loan_amnt, 10540.0)
        self.assertEqual(application.loan_grade, "C")
        self.assertTrue(prediction.shap_explanations)
        self.assertTrue(CreditRecommendation.objects.filter(prediction=prediction).exists())


class PredictionArtifactRecoveryTests(TestCase):
    @patch("ml_engine.prediction_model.service.train_and_save_artifacts")
    def test_incompatible_artifacts_trigger_rebuild(self, train_mock):
        engine = CreditRiskEngine.__new__(CreditRiskEngine)
        engine._ensure_artifacts = MagicMock()

        def assign_side_effect():
            if not hasattr(assign_side_effect, "attempts"):
                assign_side_effect.attempts = 0
            assign_side_effect.attempts += 1
            if assign_side_effect.attempts == 1:
                raise ModuleNotFoundError("No module named 'numpy._core'")
            engine.rf_model = object()
            engine.lr_model = object()
            engine.scaler = object()
            engine.label_encoders = {}
            engine.feature_names = []
            engine.metadata = {}

        engine._assign_loaded_artifacts = MagicMock(side_effect=assign_side_effect)

        engine._load_runtime_artifacts()

        engine._ensure_artifacts.assert_called_once()
        self.assertEqual(engine._assign_loaded_artifacts.call_count, 2)
        train_mock.assert_called_once()
