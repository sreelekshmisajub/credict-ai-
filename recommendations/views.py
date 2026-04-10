from django.shortcuts import render

from authentication.decorators import role_required

from .models import CreditRecommendation


@role_required("USER")
def recommendations_view(request):
    recommendations = CreditRecommendation.objects.filter(user=request.user).select_related(
        "prediction",
        "prediction__application",
    )
    return render(
        request,
        "users/recommendations.html",
        {
            "recommendations": recommendations,
            "user_section": "improvements",
            "latest_prediction": (
                request.user.loan_applications.select_related("prediction")
                .filter(prediction__isnull=False)
                .order_by("-created_at")
                .first()
                .prediction
                if request.user.loan_applications.filter(prediction__isnull=False).exists()
                else None
            ),
        },
    )
