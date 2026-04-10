from datetime import timedelta

from django.contrib import messages
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from authentication.models import LoginAudit
from bank_officer.models import BankOfficerProfile
from analytics.services import build_system_analytics, sync_latest_model_snapshot
from authentication.decorators import role_required
from credit_prediction.models import CreditPrediction, FraudAlert, LoanApplication
from users.models import CustomUser, FinancialProfile

from .forms import OfficerCreationForm, OfficerManagementForm, SystemAnnouncementForm
from .models import AdminActionLog, SystemAnnouncement


RISK_CHOICES = ("Low Risk", "Medium Risk", "High Risk")


def _admin_context(section: str, **extra):
    return {"admin_section": section, **extra}


def _application_queryset():
    return (
        LoanApplication.objects.select_related(
            "user",
            "user__financial_profile",
            "prediction",
            "reviewed_by",
        )
        .prefetch_related("associated_alerts")
        .order_by("-created_at")
    )


def _record_admin_action(actor, action_type: str, description: str):
    AdminActionLog.objects.create(
        actor=actor if getattr(actor, "role", None) == "ADMIN" else None,
        action_type=action_type,
        description=description,
    )


def _recent_activity():
    activities = []
    for member in CustomUser.objects.order_by("-date_joined")[:5]:
        activities.append(
            {
                "title": "New account registered",
                "detail": f"{member.get_full_name() or member.username} joined as {member.get_role_display().lower()}.",
                "timestamp": member.date_joined,
                "link": reverse("admin_panel:user-management"),
            }
        )
    for application in _application_queryset()[:6]:
        activities.append(
            {
                "title": "Loan application submitted",
                "detail": f"Application #{application.id} from {application.user.get_full_name() or application.user.username} for {application.loan_intent.lower()}.",
                "timestamp": application.created_at,
                "link": reverse("admin_panel:application-monitoring"),
            }
        )
    for application in _application_queryset().exclude(reviewed_at__isnull=True)[:6]:
        reviewer_name = (application.reviewed_by.get_full_name() or application.reviewed_by.username) if application.reviewed_by else "System Auto-Decision"
        activities.append(
            {
                "title": "Officer decision recorded" if application.reviewed_by else "Automated decision recorded",
                "detail": f"Application #{application.id} marked {application.get_status_display().lower()} by {reviewer_name}.",
                "timestamp": application.reviewed_at,
                "link": reverse("admin_panel:application-monitoring"),
            }
        )
    for profile in FinancialProfile.objects.select_related("user").filter(
        salary_slip__isnull=False,
        income_proof_uploaded_at__isnull=False,
    ).order_by("-income_proof_uploaded_at")[:5]:
        activities.append(
            {
                "title": "Income proof uploaded",
                "detail": f"{profile.user.get_full_name() or profile.user.username} uploaded {profile.income_proof_filename}.",
                "timestamp": profile.income_proof_uploaded_at,
                "link": reverse("admin_panel:application-monitoring"),
            }
        )
    for audit in LoginAudit.objects.select_related("user")[:5]:
        activities.append(
            {
                "title": "Authentication event",
                "detail": f"{'Successful' if audit.successful else 'Failed'} login attempt for {audit.username_attempt}.",
                "timestamp": audit.created_at,
                "link": reverse("admin_panel:activity-logs"),
            }
        )
    for action in AdminActionLog.objects.select_related("actor")[:5]:
        activities.append(
            {
                "title": action.get_action_type_display(),
                "detail": action.description,
                "timestamp": action.created_at,
                "link": reverse("admin_panel:activity-logs"),
            }
        )
    activities.sort(key=lambda item: item["timestamp"], reverse=True)
    return activities[:12]


def _weekly_application_summary(weeks: int = 4):
    today = timezone.now().date()
    summary = []
    for offset in range(weeks - 1, -1, -1):
        period_end = today - timedelta(days=offset * 7)
        period_start = period_end - timedelta(days=6)
        weekly_qs = LoanApplication.objects.filter(
            created_at__date__gte=period_start,
            created_at__date__lte=period_end,
        )
        summary.append(
            {
                "label": f"{period_start.strftime('%b %d')} - {period_end.strftime('%b %d')}",
                "approved": weekly_qs.filter(status="APPROVED").count(),
                "rejected": weekly_qs.filter(status="REJECTED").count(),
                "verification_required": weekly_qs.filter(
                    status="VERIFICATION_REQUIRED"
                ).count(),
                "pending": weekly_qs.filter(status="PENDING").count(),
            }
        )
    return summary


def _intent_risk_rows():
    rows = (
        CreditPrediction.objects.select_related("application")
        .values("application__loan_intent")
        .annotate(
            applications=Count("id"),
            avg_probability=Avg("risk_probability"),
            avg_score=Avg("credit_score"),
        )
        .order_by("-applications")
    )
    return [
        {
            "intent": row["application__loan_intent"].replace("_", " ").title(),
            "applications": row["applications"],
            "avg_probability": round((row["avg_probability"] or 0) * 100, 1),
            "avg_score": round(row["avg_score"] or 0),
        }
        for row in rows
    ]


def admin_entry(request):
    if request.user.is_authenticated and request.user.role == "ADMIN":
        return redirect("admin_panel:dashboard")
    return redirect("admin-login")


@role_required("ADMIN")
def dashboard(request):
    analytics = build_system_analytics()
    applications = _application_queryset()
    document_uploads = FinancialProfile.objects.filter(
        salary_slip__isnull=False
    ).count()
    recent_alerts = FraudAlert.objects.select_related("user", "application").filter(
        resolved=False
    )[:5]
    recent_announcements = SystemAnnouncement.objects.select_related("created_by")[:5]
    active_announcement_count = SystemAnnouncement.objects.filter(is_active=True).count()
    recent_logins = LoginAudit.objects.select_related("user")[:6]
    approved_count = applications.filter(status="APPROVED").count()
    rejected_count = applications.filter(status="REJECTED").count()
    pending_count = applications.filter(status="PENDING").count()
    verification_required_count = applications.filter(
        status="VERIFICATION_REQUIRED"
    ).count()
    return render(
        request,
        "admin/dashboard.html",
        _admin_context(
            "dashboard",
            analytics=analytics,
            total_users=CustomUser.objects.filter(role="USER").count(),
            total_applications=applications.count(),
            approved_count=approved_count,
            rejected_count=rejected_count,
            pending_count=pending_count,
            verification_required_count=verification_required_count,
            document_uploads=document_uploads,
            recent_alerts=recent_alerts,
            recent_announcements=recent_announcements,
            active_announcement_count=active_announcement_count,
            recent_logins=recent_logins,
            recent_activity=_recent_activity(),
            risk_chart_data=[
                {"label": label, "value": value}
                for label, value in analytics.get("risk_breakdown", {}).items()
            ],
            application_chart_data=[
                {"label": label.replace("_", " ").title(), "value": value}
                for label, value in analytics.get("application_breakdown", {}).items()
            ],
        ),
    )


@role_required("ADMIN")
def user_management(request):
    if request.method == "POST":
        user = get_object_or_404(CustomUser, pk=request.POST.get("user_id"))
        previous_role = user.role
        previous_active = user.is_active
        user.role = request.POST.get("role", user.role)
        user.is_active = request.POST.get("is_active") == "on"
        user.save(update_fields=["role", "is_active"])
        _record_admin_action(
            request.user,
            "USER_ACCESS",
            (
                f"Updated {user.email or user.username}: role {previous_role} -> {user.role}, "
                f"active {previous_active} -> {user.is_active}."
            ),
        )
        messages.success(request, f"Updated access settings for {user.username}.")
        return redirect("admin_panel:user-management")

    selected_role = (request.GET.get("role") or "").strip()
    search_query = (request.GET.get("q") or "").strip()
    users = CustomUser.objects.order_by("-date_joined")
    if selected_role in {"USER", "BANK_OFFICER", "ADMIN"}:
        users = users.filter(role=selected_role)
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
        )
    return render(
        request,
        "admin/user_management.html",
        _admin_context(
            "users",
            users=users,
            selected_role=selected_role,
            search_query=search_query,
            applicants_count=CustomUser.objects.filter(role="USER").count(),
            officers_count=CustomUser.objects.filter(role="BANK_OFFICER").count(),
            admins_count=CustomUser.objects.filter(role="ADMIN").count(),
        ),
    )


@role_required("ADMIN")
def model_monitoring(request):
    snapshot = sync_latest_model_snapshot()
    analytics = build_system_analytics()
    recent_predictions = CreditPrediction.objects.select_related(
        "application",
        "application__user",
    )[:6]
    return render(
        request,
        "admin/model_monitoring.html",
        _admin_context(
            "model-monitoring",
            snapshot=snapshot,
            analytics=analytics,
            recent_predictions=recent_predictions,
        ),
    )


@role_required("ADMIN")
def fraud_monitoring(request):
    if request.method == "POST":
        alert = get_object_or_404(FraudAlert, pk=request.POST.get("alert_id"))
        alert.resolved = True
        alert.save(update_fields=["resolved"])
        _record_admin_action(
            request.user,
            "FRAUD_REVIEW",
            f"Marked fraud alert #{alert.id} ({alert.alert_type}) as resolved.",
        )
        messages.success(request, "Fraud alert marked as resolved.")
        return redirect("admin_panel:fraud-monitoring")

    alerts = FraudAlert.objects.select_related("user", "application").order_by("-detected_at")
    selected_state = (request.GET.get("state") or "").strip()
    if selected_state == "open":
        alerts = alerts.filter(resolved=False)
    elif selected_state == "resolved":
        alerts = alerts.filter(resolved=True)
    return render(
        request,
        "admin/fraud_monitoring.html",
        _admin_context(
            "fraud-monitoring",
            alerts=alerts,
            selected_state=selected_state,
            open_count=FraudAlert.objects.filter(resolved=False).count(),
            resolved_count=FraudAlert.objects.filter(resolved=True).count(),
        ),
    )


@role_required("ADMIN")
def analytics_view(request):
    analytics = build_system_analytics()
    return render(
        request,
        "admin/analytics.html",
        _admin_context(
            "analytics",
            analytics=analytics,
            risk_chart_data=[
                {"label": label, "value": value}
                for label, value in analytics.get("risk_breakdown", {}).items()
            ],
            application_chart_data=[
                {"label": label.replace("_", " ").title(), "value": value}
                for label, value in analytics.get("application_breakdown", {}).items()
            ],
        ),
    )


@role_required("ADMIN")
def officer_management(request):
    form_type = ""
    if request.method == "POST":
        form_type = request.POST.get("form_type") or (
            "update" if request.POST.get("profile_id") else "create"
        )
    creation_form = OfficerCreationForm(
        request.POST if request.method == "POST" and form_type == "create" else None
    )
    if request.method == "POST":
        if form_type == "create" and creation_form.is_valid():
            creation_form.save()
            messages.success(request, "Bank officer account created successfully.")
            return redirect("admin_panel:officer-management")
        elif form_type == "update":
            profile = get_object_or_404(BankOfficerProfile.objects.select_related("user"), pk=request.POST.get("profile_id"))
            form = OfficerManagementForm(request.POST, instance=profile)
            if form.is_valid():
                form.save()
                _record_admin_action(
                    request.user,
                    "OFFICER_ACCESS",
                    f"Updated officer {profile.user.email or profile.user.username}."
                )
                messages.success(request, "Officer updated.")
            else:
                messages.error(request, "Update failed.")
            return redirect("admin_panel:officer-management")

    officers = BankOfficerProfile.objects.select_related("user").order_by("organization_name")
    officer_rows = [
        {"profile": p, "form": OfficerManagementForm(instance=p)}
        for p in officers
    ]
    return render(
        request,
        "admin/officer_management.html",
        _admin_context(
            "officers",
            officer_rows=officer_rows,
            creation_form=creation_form,
            officers_count=officers.count(),
            active_officers=officers.filter(user__is_active=True).count(),
            inactive_officers=officers.filter(user__is_active=False).count(),
        ),
    )


@role_required("ADMIN")
def application_monitoring(request):
    applications = _application_queryset()
    selected_status = (request.GET.get("status") or "").strip()
    selected_risk = (request.GET.get("risk") or "").strip()
    search_query = (request.GET.get("q") or "").strip()
    if selected_status in {choice[0] for choice in LoanApplication.STATUS_CHOICES}:
        applications = applications.filter(status=selected_status)
    if selected_risk in RISK_CHOICES:
        applications = applications.filter(prediction__risk_category=selected_risk)
    if search_query:
        applications = applications.filter(
            Q(user__email__icontains=search_query)
            | Q(user__first_name__icontains=search_query)
            | Q(user__last_name__icontains=search_query)
            | Q(loan_intent__icontains=search_query)
        )
    return render(
        request,
        "admin/application_monitoring.html",
        _admin_context(
            "applications",
            applications=applications,
            selected_status=selected_status,
            selected_risk=selected_risk,
            search_query=search_query,
            status_options=LoanApplication.STATUS_CHOICES,
            risk_options=RISK_CHOICES,
            total_application_count=LoanApplication.objects.count(),
            total_prediction_count=CreditPrediction.objects.count(),
            open_document_count=FinancialProfile.objects.filter(
                income_proof_status="PENDING"
            ).count(),
        ),
    )


@role_required("ADMIN")
def announcements(request):
    form = SystemAnnouncementForm(request.POST or None)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "toggle":
            announcement = get_object_or_404(SystemAnnouncement, pk=request.POST.get("announcement_id"))
            announcement.is_active = not announcement.is_active
            announcement.save(update_fields=["is_active"])
            _record_admin_action(
                request.user,
                "ANNOUNCEMENT",
                f"{'Activated' if announcement.is_active else 'Deactivated'} announcement '{announcement.title}'.",
            )
            messages.success(request, "Announcement status updated successfully.")
            return redirect("admin_panel:announcements")
        if form.is_valid():
            announcement = form.save(commit=False)
            announcement.created_by = request.user
            announcement.save()
            _record_admin_action(
                request.user,
                "ANNOUNCEMENT",
                f"Created announcement '{announcement.title}' for {announcement.get_audience_display().lower()}.",
            )
            messages.success(request, "Announcement published successfully.")
            return redirect("admin_panel:announcements")

    return render(
        request,
        "admin/announcements.html",
        _admin_context(
            "announcements",
            form=form,
            announcements=SystemAnnouncement.objects.select_related("created_by"),
            active_announcement_count=SystemAnnouncement.objects.filter(is_active=True).count(),
            inactive_announcement_count=SystemAnnouncement.objects.filter(is_active=False).count(),
        ),
    )


@role_required("ADMIN")
def activity_logs(request):
    recent_documents = FinancialProfile.objects.select_related("user").filter(
        salary_slip__isnull=False
    ).order_by("-income_proof_uploaded_at", "-updated_at")[:12]
    recent_reviews = _application_queryset().exclude(reviewed_at__isnull=True)[:12]
    return render(
        request,
        "admin/activity_logs.html",
        _admin_context(
            "activity-logs",
            login_audits=LoginAudit.objects.select_related("user")[:20],
            admin_actions=AdminActionLog.objects.select_related("actor")[:20],
            recent_documents=recent_documents,
            recent_reviews=recent_reviews,
            login_audit_count=LoginAudit.objects.count(),
            admin_action_count=AdminActionLog.objects.count(),
        ),
    )


@role_required("ADMIN")
def risk_analysis(request):
    analytics = build_system_analytics()
    intent_risk_rows = _intent_risk_rows()
    approved_count = LoanApplication.objects.filter(status="APPROVED").count()
    rejected_count = LoanApplication.objects.filter(status="REJECTED").count()
    if rejected_count:
        approval_odds = f"1:{approved_count / rejected_count:.1f}"
    elif approved_count:
        approval_odds = "1:0.0"
    else:
        approval_odds = "--"
    return render(
        request,
        "admin/risk_analysis.html",
        _admin_context(
            "risk-analysis",
            analytics=analytics,
            intent_risk_rows=intent_risk_rows,
            weekly_application_summary=_weekly_application_summary(),
            approval_odds=approval_odds,
        ),
    )


@role_required("ADMIN")
def document_verification(request):
    profiles = FinancialProfile.objects.select_related("user").exclude(
        salary_slip=""
    ).order_by("-income_proof_uploaded_at")
    
    # Simple search for document management
    q = request.GET.get("q", "")
    if q:
        profiles = profiles.filter(
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q) |
            Q(user__email__icontains=q)
        )

    return render(
        request,
        "admin/document_verification.html",
        _admin_context(
            "document-verification",
            profiles=profiles,
            search_query=q,
            verification_queue_count=profiles.count(),
            verified_document_count=FinancialProfile.objects.filter(
                income_proof_status="VERIFIED"
            ).count(),
            pending_document_count=FinancialProfile.objects.filter(
                income_proof_status="PENDING"
            ).count(),
            rejected_document_count=FinancialProfile.objects.filter(
                income_proof_status="REJECTED"
            ).count(),
        ),
    )


@role_required("ADMIN")
def risk_configuration(request):
    from .models import RiskConfiguration
    config = RiskConfiguration.get_solo()
    analytics = build_system_analytics()
    
    if request.method == "POST":
        config.auto_decision_enabled = request.POST.get("auto_decision") == "on"
        config.approval_threshold = float(request.POST.get("approval_threshold", config.approval_threshold))
        config.rejection_threshold = float(request.POST.get("rejection_threshold", config.rejection_threshold))
        config.updated_by = request.user
        config.save()
        
        _record_admin_action(
            request.user,
            "RISK_CONFIG",
            f"Updated risk rules: Auto={config.auto_decision_enabled}, Appr={config.approval_threshold}, Rej={config.rejection_threshold}."
        )
        messages.success(request, "Risk rules and thresholds updated successfully.")
        return redirect("admin_panel:risk-configuration")

    return render(
        request,
        "admin/risk_configuration.html",
        _admin_context(
            "risk-configuration",
            config=config,
            analytics=analytics,
        ),
    )


@role_required("ADMIN")
def system_settings(request):
    from .models import RiskConfiguration

    analytics = build_system_analytics()
    snapshot = sync_latest_model_snapshot()
    return render(
        request,
        "admin/settings.html",
        _admin_context(
            "settings",
            analytics=analytics,
            snapshot=snapshot,
            risk_config=RiskConfiguration.get_solo(),
        ),
    )
