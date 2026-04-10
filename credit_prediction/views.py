from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from authentication.decorators import role_required
from recommendations.models import CreditRecommendation
from users.forms import FinancialProfileForm, LoanApplicationForm

from .models import CreditPrediction
from .services import create_prediction_workflow


@role_required("USER")
def create_prediction(request):
    profile_instance = getattr(request.user, "financial_profile", None)
    selected_home_ownership = (
        request.POST.get("profile-person_home_ownership")
        if request.method == "POST"
        else getattr(profile_instance, "person_home_ownership", None)
    )
    financial_form = FinancialProfileForm(
        request.POST or None,
        request.FILES or None,
        instance=profile_instance,
        prefix="profile",
        require_income_proof=True,
    )
    application_form = LoanApplicationForm(
        request.POST or None,
        prefix="loan",
        profile_home_ownership=selected_home_ownership,
    )

    if request.method == "POST" and financial_form.is_valid() and application_form.is_valid():
        application, prediction = create_prediction_workflow(
            request.user,
            financial_form.build_profile_defaults(),
            application_form.cleaned_data,
        )
        messages.success(request, "Credit analysis completed successfully.")
        return redirect(f"{reverse('users:credit-score')}?prediction={prediction.id}")

    latest_prediction = (
        CreditPrediction.objects.filter(application__user=request.user)
        .select_related("application")
        .order_by("-created_at")
        .first()
    )
    document_status = {
        "status": (
            profile_instance.get_income_proof_status_display()
            if profile_instance
            else "Not Submitted"
        ),
        "uploaded_at": getattr(profile_instance, "income_proof_uploaded_at", None),
        "document_name": (
            profile_instance.income_proof_filename if profile_instance else ""
        ),
        "document_url": (
            profile_instance.salary_slip.url
            if profile_instance and profile_instance.salary_slip
            else ""
        ),
    }
    return render(
        request,
        "users/financial_data.html",
        {
            "user_section": "financial-data",
            "financial_form": financial_form,
            "application_form": application_form,
            "latest_prediction": latest_prediction,
            "document_status": document_status,
        },
    )


@login_required
def prediction_detail(request, prediction_id):
    prediction = get_object_or_404(
        CreditPrediction.objects.select_related("application", "application__user"),
        pk=prediction_id,
    )
    if request.user.role == "USER" and prediction.application.user_id != request.user.id:
        raise Http404("Prediction not found.")
    recommendations = CreditRecommendation.objects.filter(prediction=prediction)
    alerts = prediction.application.associated_alerts.all()
    return render(
        request,
        "users/prediction_detail.html",
        {
            "prediction": prediction,
            "application": prediction.application,
            "recommendations": recommendations,
            "alerts": alerts,
        },
    )
