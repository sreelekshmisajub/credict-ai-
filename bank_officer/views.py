from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from admin_panel.models import SystemAnnouncement
from analytics.services import build_system_analytics
from authentication.decorators import role_required
from credit_prediction.models import FraudAlert, LoanApplication
from credit_prediction.services import review_application
from recommendations.models import CreditRecommendation
from users.models import CustomUser

from .forms import (
    BankOfficerProfileForm,
    IncomeProofReviewForm,
    OfficerAccountForm,
    OfficerDecisionForm,
)


RISK_CHOICES = ("Low Risk", "Medium Risk", "High Risk")


def _officer_context(section: str, **extra):
    return {"officer_section": section, **extra}


def _application_queryset():
    return (
        LoanApplication.objects.select_related(
            "user",
            "user__financial_profile",
            "prediction",
            "reviewed_by",
        )
        .prefetch_related("associated_alerts", "prediction__recommendations")
        .order_by("-created_at")
    )


def _scored_application(application_id: int):
    return get_object_or_404(
        _application_queryset().filter(prediction__isnull=False),
        pk=application_id,
    )


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


@role_required("BANK_OFFICER")
def dashboard(request):
    applications = _application_queryset()
    risk_breakdown = {
        row["prediction__risk_category"]: row["total"]
        for row in applications.filter(prediction__isnull=False)
        .values("prediction__risk_category")
        .annotate(total=Count("id"))
        .order_by("-total")
    }
    recent_activity = applications[:6]
    recent_alerts = FraudAlert.objects.filter(resolved=False).select_related(
        "user",
        "application",
    )[:5]
    pending_income_proof_count = applications.filter(
        user__financial_profile__salary_slip__isnull=False,
        user__financial_profile__income_proof_status="PENDING",
    ).count()
    context = _officer_context(
        "dashboard",
        total_applications=applications.count(),
        pending_count=applications.filter(status="PENDING").count(),
        approved_count=applications.filter(status="APPROVED").count(),
        rejected_count=applications.filter(status="REJECTED").count(),
        verification_required_count=applications.filter(
            status="VERIFICATION_REQUIRED"
        ).count(),
        pending_income_proof_count=pending_income_proof_count,
        open_alerts=FraudAlert.objects.filter(resolved=False).count(),
        recent_activity=recent_activity,
        recent_alerts=recent_alerts,
        risk_breakdown=risk_breakdown,
    )
    return render(request, "officer/dashboard.html", context)


@role_required("BANK_OFFICER")
def applications(request):
    queryset = _application_queryset()
    search_query = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "").strip()
    selected_risk = request.GET.get("risk", "").strip()

    if search_query:
        search_filter = (
            Q(user__username__icontains=search_query)
            | Q(user__email__icontains=search_query)
            | Q(user__first_name__icontains=search_query)
            | Q(user__last_name__icontains=search_query)
            | Q(loan_intent__icontains=search_query)
        )
        if search_query.isdigit():
            search_filter |= Q(id=int(search_query))
        queryset = queryset.filter(search_filter)

    valid_statuses = {choice[0] for choice in LoanApplication.STATUS_CHOICES}
    if selected_status in valid_statuses:
        queryset = queryset.filter(status=selected_status)

    if selected_risk in RISK_CHOICES:
        queryset = queryset.filter(prediction__risk_category=selected_risk)

    context = _officer_context(
        "applications",
        applications=queryset,
        search_query=search_query,
        selected_status=selected_status,
        selected_risk=selected_risk,
        status_options=LoanApplication.STATUS_CHOICES,
        risk_options=RISK_CHOICES,
    )
    return render(request, "officer/applications.html", context)


@role_required("BANK_OFFICER")
def application_detail(request, application_id):
    application = get_object_or_404(_application_queryset(), pk=application_id)
    financial_profile = getattr(application.user, "financial_profile", None)
    initial_decision = (
        application.status
        if application.status in dict(OfficerDecisionForm.DECISION_CHOICES)
        else "APPROVED"
    )
    form = OfficerDecisionForm(
        request.POST or None,
        initial={
            "decision": initial_decision,
            "decision_notes": application.decision_notes,
        },
    )
    income_proof_form = (
        IncomeProofReviewForm(
            request.POST if "income_proof_status" in request.POST else None,
            initial={
                "income_proof_status": (
                    financial_profile.income_proof_status
                    if financial_profile and financial_profile.salary_slip
                    else "PENDING"
                )
            },
        )
        if financial_profile and financial_profile.salary_slip
        else None
    )
    if request.method == "POST":
        if "income_proof_status" in request.POST and income_proof_form and income_proof_form.is_valid():
            financial_profile.income_proof_status = income_proof_form.cleaned_data[
                "income_proof_status"
            ]
            financial_profile.save(update_fields=["income_proof_status", "updated_at"])
            messages.success(request, "Income proof review status updated successfully.")
            return redirect("bank_officer:application-detail", application_id=application.id)
        if "decision" in request.POST and form.is_valid():
            review_application(
                application,
                request.user,
                form.cleaned_data["decision"],
                form.cleaned_data["decision_notes"],
            )
            messages.success(request, "Loan decision updated successfully.")
            return redirect(
                f"{reverse('bank_officer:application-detail', args=[application.id])}"
                "?decision_saved=1#quick-decision-panel"
            )

    prediction = getattr(application, "prediction", None)
    recommendations = prediction.recommendations.all() if prediction else []
    context = _officer_context(
        "applications",
        application=application,
        prediction=prediction,
        decision_form=form,
        income_proof_form=income_proof_form,
        document_status=_document_status(financial_profile),
        alerts=application.associated_alerts.all(),
        recommendations=recommendations,
    )
    return render(request, "officer/application_detail.html", context)


@role_required("BANK_OFFICER")
def risk_analysis(request):
    applications = (
        _application_queryset()
        .filter(prediction__isnull=False)
        .order_by("-prediction__risk_probability", "-created_at")
    )
    selected_risk = request.GET.get("risk", "").strip()
    if selected_risk in RISK_CHOICES:
        applications = applications.filter(prediction__risk_category=selected_risk)

    return render(
        request,
        "officer/risk_analysis.html",
        _officer_context(
            "risk-analysis",
            applications=applications,
            selected_risk=selected_risk,
            risk_options=RISK_CHOICES,
        ),
    )


@role_required("BANK_OFFICER")
def risk_analysis_detail(request, application_id):
    application = _scored_application(application_id)
    prediction = application.prediction
    feature_rows = list(prediction.feature_payload.items())
    return render(
        request,
        "officer/risk_analysis_detail.html",
        _officer_context(
            "risk-analysis",
            application=application,
            prediction=prediction,
            feature_rows=feature_rows,
            document_status=_document_status(getattr(application.user, "financial_profile", None)),
            shap_chart_points=_chart_points_from_mapping(prediction.shap_explanations),
        ),
    )


@role_required("BANK_OFFICER")
def explanations(request):
    applications = (
        _application_queryset()
        .filter(prediction__isnull=False)
        .order_by("-created_at")
    )
    return render(
        request,
        "officer/explanations.html",
        _officer_context("explanations", applications=applications),
    )


@role_required("BANK_OFFICER")
def explanation_detail(request, application_id):
    application = _scored_application(application_id)
    prediction = application.prediction
    return render(
        request,
        "officer/explanation_detail.html",
        _officer_context(
            "explanations",
            application=application,
            prediction=prediction,
            document_status=_document_status(getattr(application.user, "financial_profile", None)),
            shap_chart_points=_chart_points_from_mapping(prediction.shap_explanations),
            lime_chart_points=_chart_points_from_mapping(prediction.lime_explanations),
        ),
    )


@role_required("BANK_OFFICER")
def decision(request, application_id):
    application = get_object_or_404(_application_queryset(), pk=application_id)
    financial_profile = getattr(application.user, "financial_profile", None)
    initial_decision = (
        application.status
        if application.status in dict(OfficerDecisionForm.DECISION_CHOICES)
        else "APPROVED"
    )
    form = OfficerDecisionForm(
        request.POST or None,
        initial={
            "decision": initial_decision,
            "decision_notes": application.decision_notes,
        },
    )
    if request.method == "POST" and form.is_valid():
        review_application(
            application,
            request.user,
            form.cleaned_data["decision"],
            form.cleaned_data["decision_notes"],
        )
        messages.success(request, "Officer decision saved.")
        return redirect("bank_officer:decision", application_id=application.id)

    return render(
        request,
        "officer/decision.html",
        _officer_context(
            "applications",
            application=application,
            prediction=getattr(application, "prediction", None),
            decision_form=form,
            document_status=_document_status(financial_profile),
        ),
    )


@role_required("BANK_OFFICER")
def applicant_profile(request, user_id):
    applicant = get_object_or_404(
        CustomUser.objects.select_related("financial_profile"),
        pk=user_id,
        role="USER",
    )
    applications = (
        applicant.loan_applications.select_related("prediction", "reviewed_by")
        .prefetch_related("associated_alerts")
        .order_by("-created_at")
    )
    recommendations = CreditRecommendation.objects.filter(user=applicant).select_related(
        "prediction"
    )[:6]
    return render(
        request,
        "officer/applicant_profile.html",
        _officer_context(
            "applications",
            applicant=applicant,
            applications=applications,
            recommendations=recommendations,
            document_status=_document_status(getattr(applicant, "financial_profile", None)),
        ),
    )


@role_required("BANK_OFFICER")
def fraud_alerts(request):
    all_alerts = FraudAlert.objects.select_related("user", "application").order_by(
        "-detected_at"
    )
    selected_severity = request.GET.get("severity", "").strip()
    selected_state = request.GET.get("state", "").strip()
    valid_severities = {choice[0] for choice in FraudAlert.SEVERITY_CHOICES}
    alerts = all_alerts
    if selected_severity in valid_severities:
        alerts = alerts.filter(severity=selected_severity)
    if selected_state == "open":
        alerts = alerts.filter(resolved=False)
    elif selected_state == "resolved":
        alerts = alerts.filter(resolved=True)

    open_alert_count = all_alerts.filter(resolved=False).count()
    resolved_alert_count = all_alerts.filter(resolved=True).count()
    critical_alert_count = all_alerts.filter(severity="CRITICAL").count()
    return render(
        request,
        "officer/fraud_alerts.html",
        _officer_context(
            "fraud-alerts",
            alerts=alerts,
            selected_severity=selected_severity,
            selected_state=selected_state,
            severity_options=FraudAlert.SEVERITY_CHOICES,
            open_alert_count=open_alert_count,
            resolved_alert_count=resolved_alert_count,
            critical_alert_count=critical_alert_count,
            total_alert_count=open_alert_count + resolved_alert_count,
        ),
    )


@role_required("BANK_OFFICER")
def reports(request):
    analytics = build_system_analytics()
    applications = LoanApplication.objects.all()
    approval_denominator = applications.filter(status__in=["APPROVED", "REJECTED"]).count()
    approval_rate = (
        (applications.filter(status="APPROVED").count() / approval_denominator) * 100
        if approval_denominator
        else 0
    )
    fraud_breakdown = {
        row["severity"]: row["total"]
        for row in FraudAlert.objects.values("severity")
        .annotate(total=Count("id"))
        .order_by("-total")
    }
    return render(
        request,
        "officer/reports.html",
        _officer_context(
            "reports",
            analytics=analytics,
            approval_rate=approval_rate,
            review_backlog=applications.filter(status="PENDING").count(),
            verification_required_count=applications.filter(
                status="VERIFICATION_REQUIRED"
            ).count(),
            fraud_breakdown=fraud_breakdown,
        ),
    )


@role_required("BANK_OFFICER")
def notifications(request):
    new_applications = _application_queryset().filter(status="PENDING")[:6]
    verification_requests = _application_queryset().filter(
        status="VERIFICATION_REQUIRED"
    )[:6]
    document_reviews = _application_queryset().filter(
        user__financial_profile__salary_slip__isnull=False,
        user__financial_profile__income_proof_status="PENDING",
    )[:6]
    fraud_notifications = FraudAlert.objects.filter(resolved=False).select_related(
        "user",
        "application",
    )[:6]
    announcements = SystemAnnouncement.objects.filter(
        is_active=True,
    ).filter(Q(audience="ALL") | Q(audience="BANK_OFFICER"))
    return render(
        request,
        "officer/notifications.html",
        _officer_context(
            "notifications",
            new_applications=new_applications,
            verification_requests=verification_requests,
            document_reviews=document_reviews,
            fraud_notifications=fraud_notifications,
            announcements=announcements[:6],
        ),
    )


@role_required("BANK_OFFICER")
def profile(request):
    profile_instance = getattr(request.user, "bank_officer_profile", None)
    action = request.POST.get("form_action")
    account_form = OfficerAccountForm(
        request.POST if action == "account" else None,
        instance=request.user,
        prefix="account",
    )
    profile_form = BankOfficerProfileForm(
        request.POST if action == "account" else None,
        instance=profile_instance,
        prefix="profile",
    )
    password_form = _styled_password_form(
        request.user,
        request.POST if action == "security" else None,
    )

    if request.method == "POST":
        if action == "account" and account_form.is_valid() and profile_form.is_valid():
            account_form.save()
            officer_profile = profile_form.save(commit=False)
            officer_profile.user = request.user
            officer_profile.save()
            messages.success(request, "Officer profile updated successfully.")
            return redirect("bank_officer:profile")

        if action == "security" and password_form.is_valid():
            user = password_form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Password updated successfully.")
            return redirect("bank_officer:profile")

    return render(
        request,
        "officer/profile.html",
        _officer_context(
            "profile",
            account_form=account_form,
            profile_form=profile_form,
            password_form=password_form,
            officer_profile=profile_instance,
            approval_limit=(
                profile_instance.approval_limit if profile_instance else None
            ),
        ),
    )


@role_required("BANK_OFFICER")
def document_verification(request):
    applications = _application_queryset().filter(
        user__financial_profile__salary_slip__isnull=False
    ).order_by("-user__financial_profile__updated_at")
    
    return render(
        request,
        "officer/document_verification.html",
        _officer_context(
            "verification",
            applications=applications,
        ),
    )

