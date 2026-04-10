from rest_framework import serializers
from .models import LoanApplication, CreditPrediction, FraudAlert
from recommendations.models import CreditRecommendation
from users.serializers import UserSerializer


class CreditRecommendationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditRecommendation
        fields = ["id", "category", "message", "priority", "created_at"]

class LoanApplicationSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    reviewed_by = UserSerializer(read_only=True)
    prediction = serializers.SerializerMethodField()

    class Meta:
        model = LoanApplication
        fields = "__all__"

    def get_prediction(self, obj):
        if hasattr(obj, "prediction"):
            return CreditPredictionSerializer(obj.prediction).data
        return None

class CreditPredictionSerializer(serializers.ModelSerializer):
    recommendations = CreditRecommendationSerializer(many=True, read_only=True)

    class Meta:
        model = CreditPrediction
        fields = "__all__"

class FraudAlertSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = FraudAlert
        fields = "__all__"
