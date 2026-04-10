from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from admin_panel.models import SystemAnnouncement
from authentication.decorators import role_required
from credit_prediction.models import CreditPrediction, FraudAlert
from credit_prediction.services import create_prediction_workflow
from recommendations.models import CreditRecommendation

from .forms import (
    ApplicantAccountForm,
    FinancialProfileForm,
    LoanApplicationForm,
)


def _user_context(section: str, **extra):
    return {"user_section": section, **extra}


def _application_queryset(user):
    return (
        user.loan_applications.select_related("prediction", "reviewed_by")
        .prefetch_related("associated_alerts", "prediction__recommendations")
        .order_by("-created_at")
    )


def _prediction_queryset(user):
    return CreditPrediction.objects.filter(application__user=user).select_related(
        "application",
        "application__reviewed_by",
    ).order_by("-created_at")


def _selected_prediction(request, user):
    prediction_id = (request.GET.get("prediction") or "").strip()
    queryset = _prediction_queryset(user)
    if prediction_id:
        if not prediction_id.isdigit():
            raise Http404("Prediction not found.")
        prediction = queryset.filter(pk=int(prediction_id)).first()
        if prediction is None:
            raise Http404("Prediction not found.")
        return prediction
    return queryset.first()


def _styled_password_form(user, data=None):
    form = PasswordChangeForm(user=user, data=data)
    for field in form.fields.values():
        field.widget.attrs.setdefault("class", "form-control")
    return form


def _document_status(profile):
    if not profile:
        return {
            "status": "Not Submitted",
            "uploaded_at": None,
            "document_name": "",
            "document_url": "",
        }
    return {
        "status": profile.get_income_proof_status_display(),
        "uploaded_at": profile.income_proof_uploaded_at,
        "document_name": profile.income_proof_filename,
        "document_url": profile.salary_slip.url if profile.salary_slip else "",
    }


def _numeric_explanation_value(value):
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _chart_points_from_mapping(mapping):
    return [
        {"label": label, "value": _numeric_explanation_value(value)}
        for label, value in (mapping or {}).items()
    ]


def _explanation_detail_rows(mapping, scope: str):
    rows = []
    for label, raw_value in (mapping or {}).items():
        numeric_value = _numeric_explanation_value(raw_value)
        if numeric_value > 0:
            direction = "upward"
        elif numeric_value < 0:
            direction = "downward"
        else:
            direction = "neutral"

        if scope == "shap":
            if direction == "neutral":
                detail = f"{label} had little visible effect in the SHAP view."
            else:
                detail = (
                    f"{label} pushed the model outcome {direction} in the SHAP view "
                    f"with a contribution of {raw_value}."
                )
        else:
            if direction == "neutral":
                detail = f"{label} had little visible effect in the LIME view."
            else:
                detail = (
                    f"This local rule pushed the current prediction {direction} in the "
                    f"LIME view with a weight of {raw_value}."
                )

        rows.append(
            {
                "label": label,
                "value": raw_value,
                "detail": detail,
                "is_negative": numeric_value < 0,
                "is_positive": numeric_value > 0,
            }
        )
    return rows


def _score_trend_points(user):
    recent_predictions = list(_prediction_queryset(user)[:12])
    recent_predictions.reverse()
    return [
        {
            "label": prediction.created_at.strftime("%b %d"),
            "score": prediction.credit_score,
            "risk": prediction.risk_category,
        }
        for prediction in recent_predictions
    ]


def _application_volume_points(user):
    labels_to_counts = {}
    recent_applications = list(user.loan_applications.order_by("-created_at")[:12])
    recent_applications.reverse()
    for application in recent_applications:
        label = application.created_at.strftime("%b %d")
        labels_to_counts[label] = labels_to_counts.get(label, 0) + 1
    return [
        {"label": label, "count": count}
        for label, count in labels_to_counts.items()
    ]


def _dashboard_notifications(user, profile):
    entries = []
    for prediction in _prediction_queryset(user)[:3]:
        entries.append(
            {
                "title": "Credit analysis completed",
                "detail": f"Score {prediction.credit_score} with {prediction.risk_category} is ready to review.",
                "timestamp": prediction.created_at,
                "link": f"{reverse('users:credit-score')}?prediction={prediction.id}",
            }
        )
    for application in _application_queryset(user).exclude(status="PENDING")[:3]:
        detail = (
            f"{application.loan_intent} request is now {application.get_status_display().lower()}."
        )
        if application.reviewed_by:
            reviewer_name = application.reviewed_by.get_full_name() or application.reviewed_by.username
            detail = f"{detail} Reviewed by {reviewer_name}."
        if application.decision_notes:
            detail = f"{detail} {application.decision_notes}"
        entries.append(
            {
                "title": "Loan application updated",
                "detail": detail,
                "timestamp": application.reviewed_at or application.created_at,
                "link": (
                    f"{reverse('users:credit-score')}?prediction={application.prediction.id}"
                    if hasattr(application, "prediction")
                    else reverse("users:history")
                ),
            }
        )
    for alert in user.fraud_alerts.filter(resolved=False)[:2]:
        entries.append(
            {
                "title": "Fraud alert generated",
                "detail": alert.description,
                "timestamp": alert.detected_at,
                "link": reverse("users:fraud-alerts"),
            }
        )
    if profile and profile.income_proof_uploaded_at:
        entries.append(
            {
                "title": "Income proof status",
                "detail": f"Document status: {profile.get_income_proof_status_display()}.",
                "timestamp": profile.income_proof_uploaded_at,
                "link": reverse("users:profile"),
            }
        )
    for announcement in SystemAnnouncement.objects.filter(is_active=True).filter(
        Q(audience="ALL") | Q(audience="USER")
    )[:2]:
        entries.append(
            {
                "title": announcement.title,
                "detail": announcement.message,
                "timestamp": announcement.created_at,
                "link": reverse("users:notifications"),
            }
        )
    entries.sort(key=lambda item: item["timestamp"], reverse=True)
    return entries[:6]


@role_required("USER")
def dashboard(request):
    applications = list(_application_queryset(request.user)[:6])
    prediction_queryset = _prediction_queryset(request.user)
    predictions = list(prediction_queryset[:6])
    latest_prediction = predictions[0] if predictions else None
    financial_profile = getattr(request.user, "financial_profile", None)
    recent_alerts = request.user.fraud_alerts.select_related("application").filter(
        resolved=False
    )[:5]
    recommendations = CreditRecommendation.objects.filter(user=request.user)[:5]
    return render(
        request,
        "users/dashboard.html",
        _user_context(
            "dashboard",
            applications=applications,
            latest_prediction=latest_prediction,
            predictions=predictions,
            recommendations=recommendations,
            recent_alerts=recent_alerts,
            total_applications=request.user.loan_applications.count(),
            total_predictions=prediction_queryset.count(),
            open_fraud_alerts=request.user.fraud_alerts.filter(resolved=False).count(),
            financial_profile=financial_profile,
            risk_breakdown={
                "Low Risk": prediction_queryset.filter(risk_category="Low Risk").count(),
                "Medium Risk": prediction_queryset.filter(
                    risk_category="Medium Risk"
                ).count(),
                "High Risk": prediction_queryset.filter(risk_category="High Risk").count(),
            },
            score_trend_points=_score_trend_points(request.user),
            application_volume_points=_application_volume_points(request.user),
            latest_shap_points=(
                _chart_points_from_mapping(latest_prediction.shap_explanations)
                if latest_prediction
                else []
            ),
            latest_lime_points=(
                _chart_points_from_mapping(latest_prediction.lime_explanations)
                if latest_prediction
                else []
            ),
            notification_feed=_dashboard_notifications(request.user, financial_profile),
            document_status=_document_status(financial_profile),
        ),
    )


@role_required("USER")
def financial_data(request):
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
        user=request.user,
    )
    application_form = LoanApplicationForm(
        request.POST or None,
        prefix="loan",
        profile_home_ownership=selected_home_ownership,
    )
    latest_prediction = _prediction_queryset(request.user).first()

    if request.method == "POST" and financial_form.is_valid() and application_form.is_valid():
        application, prediction = create_prediction_workflow(
            request.user,
            financial_form.build_profile_defaults(),
            application_form.cleaned_data,
        )
        messages.success(request, "Credit analysis completed successfully.")
        return redirect(f"{reverse('users:credit-score')}?prediction={prediction.id}")

    return render(
        request,
        "users/financial_data.html",
        _user_context(
            "financial-data",
            financial_form=financial_form,
            application_form=application_form,
            latest_prediction=latest_prediction,
            document_status=_document_status(profile_instance),
        ),
    )


@role_required("USER")
def credit_score(request):
    prediction = _selected_prediction(request, request.user)
    prediction_choices = _prediction_queryset(request.user)[:8]
    application = prediction.application if prediction else None
    financial_profile = getattr(request.user, "financial_profile", None)
    return render(
        request,
        "users/credit_score.html",
        _user_context(
            "credit-score",
            prediction=prediction,
            application=application,
            prediction_choices=prediction_choices,
            document_status=_document_status(financial_profile),
        ),
    )


@role_required("USER")
def explanation(request):
    prediction = _selected_prediction(request, request.user)
    prediction_choices = _prediction_queryset(request.user)[:8]
    application = prediction.application if prediction else None
    recommendations = (
        CreditRecommendation.objects.filter(prediction=prediction)
        if prediction
        else CreditRecommendation.objects.none()
    )
    alerts = application.associated_alerts.all() if application else []
    return render(
        request,
        "users/explanation.html",
        _user_context(
            "explanation",
            prediction=prediction,
            application=application,
            prediction_choices=prediction_choices,
            recommendations=recommendations,
            alerts=alerts,
            shap_chart_points=(
                _chart_points_from_mapping(prediction.shap_explanations)
                if prediction
                else []
            ),
            lime_chart_points=(
                _chart_points_from_mapping(prediction.lime_explanations)
                if prediction
                else []
            ),
            shap_detail_rows=(
                _explanation_detail_rows(prediction.shap_explanations, "shap")
                if prediction
                else []
            ),
            lime_detail_rows=(
                _explanation_detail_rows(prediction.lime_explanations, "lime")
                if prediction
                else []
            ),
            feature_payload_rows=list((prediction.feature_payload or {}).items())
            if prediction
            else [],
        ),
    )


@role_required("USER")
def improvements(request):
    recommendations = CreditRecommendation.objects.filter(user=request.user).select_related(
        "prediction",
        "prediction__application",
    )
    latest_prediction = _prediction_queryset(request.user).first()
    return render(
        request,
        "users/recommendations.html",
        _user_context(
            "improvements",
            recommendations=recommendations,
            latest_prediction=latest_prediction,
            score_trend_points=_score_trend_points(request.user),
        ),
    )


@role_required("USER")
def history(request):
    applications = _application_queryset(request.user)
    return render(
        request,
        "users/history.html",
        _user_context("history", applications=applications),
    )


@role_required("USER")
def fraud_alerts(request):
    all_alerts = request.user.fraud_alerts.select_related("application").order_by(
        "-detected_at"
    )
    selected_state = (request.GET.get("state") or "").strip()
    alerts = all_alerts
    if selected_state == "open":
        alerts = alerts.filter(resolved=False)
    elif selected_state == "resolved":
        alerts = alerts.filter(resolved=True)

    open_alert_count = all_alerts.filter(resolved=False).count()
    resolved_alert_count = all_alerts.filter(resolved=True).count()
    total_alert_count = open_alert_count + resolved_alert_count
    return render(
        request,
        "users/fraud_alerts.html",
        _user_context(
            "fraud-alerts",
            alerts=alerts,
            selected_state=selected_state,
            open_alert_count=open_alert_count,
            resolved_alert_count=resolved_alert_count,
            total_alert_count=total_alert_count,
        ),
    )


@role_required("USER")
def profile(request):
    profile_instance = getattr(request.user, "financial_profile", None)
    applicant_profile = getattr(request.user, "applicant_profile", None)
    action = request.POST.get("form_action")
    account_form = ApplicantAccountForm(
        request.POST if action == "account" else None,
        request.FILES if action == "account" else None,
        instance=request.user,
        prefix="account",
    )
    financial_form = FinancialProfileForm(
        request.POST if action == "account" else None,
        request.FILES if action == "account" else None,
        instance=profile_instance,
        prefix="profile",
        user=request.user,
    )
    password_form = _styled_password_form(
        request.user,
        request.POST if action == "security" else None,
    )

    if request.method == "POST":
        if action == "account" and account_form.is_valid() and financial_form.is_valid():
            account_form.save()
            profile = financial_form.save(commit=False)
            profile.user = request.user
            profile.save()
            messages.success(request, "Your profile has been updated successfully.")
            return redirect("users:profile")

        if action == "security" and password_form.is_valid():
            user = password_form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Your password has been updated successfully.")
            return redirect("users:profile")

    return render(
        request,
        "users/profile.html",
        _user_context(
            "profile",
            account_form=account_form,
            financial_form=financial_form,
            password_form=password_form,
            applicant_profile=applicant_profile,
            document_status=_document_status(profile_instance),
        ),
    )


@role_required("USER")
def notifications(request):
    financial_profile = getattr(request.user, "financial_profile", None)
    prediction_notifications = list(_prediction_queryset(request.user)[:6])
    application_updates = list(
        _application_queryset(request.user).exclude(status="PENDING")[:6]
    )
    fraud_notifications = list(
        request.user.fraud_alerts.select_related("application").filter(resolved=False)[:6]
    )
    announcements = list(
        SystemAnnouncement.objects.filter(is_active=True).filter(
        Q(audience="ALL") | Q(audience="USER")
    )[:6]
    )
    notification_feed = _dashboard_notifications(request.user, financial_profile)
    return render(
        request,
        "users/notifications.html",
        _user_context(
            "notifications",
            prediction_notifications=prediction_notifications,
            application_updates=application_updates,
            fraud_notifications=fraud_notifications,
            announcements=announcements,
            notification_feed=notification_feed,
            prediction_notification_count=len(prediction_notifications),
            application_update_count=len(application_updates),
            fraud_notification_count=len(fraud_notifications),
            announcement_count=len(announcements),
            document_status=_document_status(financial_profile),
        ),
    )


@role_required("USER")
def documents(request):
    profile_instance = getattr(request.user, "financial_profile", None)
    action = request.POST.get("form_action")
    
    financial_form = FinancialProfileForm(
        request.POST if action == "upload" else None,
        request.FILES if action == "upload" else None,
        instance=profile_instance,
        prefix="profile",
        user=request.user,
    )

    if request.method == "POST" and action == "upload":
        if financial_form.is_valid():
            profile = financial_form.save(commit=False)
            profile.user = request.user
            profile.save()
            messages.success(request, "Document uploaded and submitted for verification.")
            return redirect("users:documents")

    return render(
        request,
        "users/documents.html",
        _user_context(
            "documents",
            financial_form=financial_form,
            document_status=_document_status(profile_instance),
            profile=profile_instance,
        ),
    )
