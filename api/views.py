from django.contrib.auth import authenticate, login, logout
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.urls import reverse
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_panel.models import AdminActionLog, SystemAnnouncement
from analytics.services import build_system_analytics, sync_latest_model_snapshot
from authentication.models import LoginAudit
from bank_officer.models import BankOfficerProfile
from credit_prediction.models import CreditPrediction, FraudAlert, LoanApplication
from credit_prediction.serializers import (
    CreditPredictionSerializer,
    FraudAlertSerializer,
    LoanApplicationSerializer,
)
from credit_prediction.services import create_prediction_workflow, review_application
from recommendations.models import CreditRecommendation
from users.models import CustomUser, FinancialProfile
from users.serializers import FinancialProfileSerializer, RegisterSerializer, UserSerializer

from .permissions import IsApplicant, IsBankOfficer, IsPlatformAdmin
from .serializers import (
    AdminActionLogSerializer,
    AdminAnnouncementCreateSerializer,
    AdminAnnouncementSerializer,
    AdminAnnouncementUpdateSerializer,
    AdminFinancialDocumentSerializer,
    AdminLoginAuditSerializer,
    AdminOfficerCreateSerializer,
    AdminOfficerSerializer,
    AdminOfficerUpdateSerializer,
    AdminUserUpdateSerializer,
    LoginSerializer,
    OfficerDecisionSerializer,
    PredictionRequestSerializer,
)


RISK_CHOICES = ("Low Risk", "Medium Risk", "High Risk")


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _record_admin_action(actor, action_type: str, description: str):
    AdminActionLog.objects.create(
        actor=actor if getattr(actor, "role", None) == "ADMIN" else None,
        action_type=action_type,
        description=description,
    )


def _snapshot_payload(snapshot):
    if not snapshot:
        return None
    return {
        "model_name": snapshot.model_name,
        "model_version": snapshot.model_version,
        "dataset_rows": snapshot.dataset_rows,
        "accuracy": snapshot.accuracy,
        "precision": snapshot.precision,
        "recall": snapshot.recall,
        "f1_score": snapshot.f1_score,
        "notes": snapshot.notes,
        "created_at": snapshot.created_at,
    }


def _admin_application_queryset():
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


def _admin_recent_activity():
    activities = []
    for member in CustomUser.objects.order_by("-date_joined")[:5]:
        activities.append(
            {
                "title": "New account registered",
                "detail": f"{member.get_full_name() or member.username} joined as {member.get_role_display().lower()}.",
                "timestamp": member.date_joined,
                "target": reverse("admin_panel:user-management"),
            }
        )
    for application in _admin_application_queryset()[:6]:
        activities.append(
            {
                "title": "Loan application submitted",
                "detail": f"Application #{application.id} from {application.user.get_full_name() or application.user.username} for {application.loan_intent.lower()}.",
                "timestamp": application.created_at,
                "target": reverse("admin_panel:application-monitoring"),
            }
        )
    for application in _admin_application_queryset().exclude(reviewed_at__isnull=True)[:6]:
        reviewer_name = (
            application.reviewed_by.get_full_name() or application.reviewed_by.username
            if application.reviewed_by
            else "Unknown officer"
        )
        activities.append(
            {
                "title": "Officer decision recorded",
                "detail": f"Application #{application.id} marked {application.get_status_display().lower()} by {reviewer_name}.",
                "timestamp": application.reviewed_at,
                "target": reverse("admin_panel:application-monitoring"),
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
                "target": reverse("admin_panel:application-monitoring"),
            }
        )
    for audit in LoginAudit.objects.select_related("user")[:5]:
        activities.append(
            {
                "title": "Authentication event",
                "detail": f"{'Successful' if audit.successful else 'Failed'} login attempt for {audit.username_attempt}.",
                "timestamp": audit.created_at,
                "target": reverse("admin_panel:activity-logs"),
            }
        )
    for action in AdminActionLog.objects.select_related("actor")[:5]:
        activities.append(
            {
                "title": action.get_action_type_display(),
                "detail": action.description,
                "timestamp": action.created_at,
                "target": reverse("admin_panel:activity-logs"),
            }
        )
    activities.sort(key=lambda item: item["timestamp"], reverse=True)
    return activities[:12]


class RegisterAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request, user)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["resolved_username"],
            password=serializer.validated_data["password"],
        )
        if not user:
            LoginAudit.objects.create(
                username_attempt=serializer.validated_data["resolved_username"],
                successful=False,
                ip_address=_client_ip(request),
            )
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        login(request, user)
        LoginAudit.objects.create(
            user=user,
            username_attempt=user.username,
            successful=True,
            ip_address=_client_ip(request),
        )
        return Response(UserSerializer(user).data)


class LogoutAPIView(APIView):
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class FinancialProfileAPIView(APIView):
    permission_classes = [IsApplicant]

    def get(self, request):
        profile = getattr(request.user, "financial_profile", None)
        if not profile:
            return Response({}, status=status.HTTP_200_OK)
        return Response(FinancialProfileSerializer(profile).data)

    def put(self, request):
        profile = getattr(request.user, "financial_profile", None)
        serializer = FinancialProfileSerializer(
            profile,
            data=request.data,
            partial=bool(profile),
        )
        serializer.is_valid(raise_exception=True)
        profile_instance = serializer.save(user=request.user)
        return Response(FinancialProfileSerializer(profile_instance).data)


class PredictionAPIView(APIView):
    permission_classes = [IsApplicant]

    def get(self, request):
        applications = LoanApplication.objects.filter(user=request.user).select_related(
            "prediction",
            "reviewed_by",
        )
        return Response(LoanApplicationSerializer(applications, many=True).data)

    def post(self, request):
        serializer = PredictionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile_data, application_data = serializer.split_payload()
        application, prediction = create_prediction_workflow(
            request.user,
            profile_data,
            application_data,
        )
        payload = LoanApplicationSerializer(application).data
        payload["prediction"] = CreditPredictionSerializer(prediction).data
        return Response(payload, status=status.HTTP_201_CREATED)


class PredictionDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, prediction_id):
        prediction = get_object_or_404(
            CreditPrediction.objects.select_related("application", "application__user"),
            pk=prediction_id,
        )
        if request.user.role == "USER" and prediction.application.user_id != request.user.id:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(CreditPredictionSerializer(prediction).data)


class ExplanationAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, prediction_id):
        prediction = get_object_or_404(
            CreditPrediction.objects.select_related("application", "application__user"),
            pk=prediction_id,
        )
        if request.user.role == "USER" and prediction.application.user_id != request.user.id:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "shap_explanations": prediction.shap_explanations,
                "lime_explanations": prediction.lime_explanations,
                "feature_payload": prediction.feature_payload,
            }
        )


class RecommendationListAPIView(APIView):
    permission_classes = [IsApplicant]

    def get(self, request):
        recommendations = CreditRecommendation.objects.filter(user=request.user)
        data = [
            {
                "id": recommendation.id,
                "category": recommendation.category,
                "message": recommendation.message,
                "priority": recommendation.priority,
                "prediction_id": recommendation.prediction_id,
            }
            for recommendation in recommendations
        ]
        return Response(data)


class OfficerApplicationListAPIView(APIView):
    permission_classes = [IsBankOfficer]

    def get(self, request):
        applications = LoanApplication.objects.select_related("user", "prediction", "reviewed_by")
        return Response(LoanApplicationSerializer(applications, many=True).data)


class OfficerDecisionAPIView(APIView):
    permission_classes = [IsBankOfficer]

    def post(self, request, application_id):
        application = get_object_or_404(LoanApplication, pk=application_id)
        serializer = OfficerDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated_application = review_application(
            application,
            request.user,
            serializer.validated_data["decision"],
            serializer.validated_data.get("decision_notes", ""),
        )
        return Response(LoanApplicationSerializer(updated_application).data)


class OfficerFraudAlertListAPIView(APIView):
    permission_classes = [IsBankOfficer]

    def get(self, request):
        alerts = FraudAlert.objects.select_related("user", "application")
        return Response(FraudAlertSerializer(alerts, many=True).data)


class AdminDashboardAPIView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        analytics = build_system_analytics()
        applications = _admin_application_queryset()
        payload = {
            "totals": {
                "users": CustomUser.objects.filter(role="USER").count(),
                "bank_officers": CustomUser.objects.filter(role="BANK_OFFICER").count(),
                "admins": CustomUser.objects.filter(role="ADMIN").count(),
                "applications": applications.count(),
            },
            "analytics": {
                **analytics,
                "latest_snapshot": _snapshot_payload(analytics.get("latest_snapshot")),
            },
            "summary": {
                "approved_count": applications.filter(status="APPROVED").count(),
                "rejected_count": applications.filter(status="REJECTED").count(),
                "pending_count": applications.filter(status="PENDING").count(),
                "verification_required_count": applications.filter(
                    status="VERIFICATION_REQUIRED"
                ).count(),
                "document_uploads": FinancialProfile.objects.filter(
                    salary_slip__isnull=False
                ).count(),
            },
            "recent_activity": _admin_recent_activity(),
            "recent_alerts": FraudAlertSerializer(
                FraudAlert.objects.select_related("user", "application").filter(
                    resolved=False
                )[:5],
                many=True,
            ).data,
            "recent_announcements": AdminAnnouncementSerializer(
                SystemAnnouncement.objects.select_related("created_by")[:5],
                many=True,
            ).data,
            "recent_logins": AdminLoginAuditSerializer(
                LoginAudit.objects.select_related("user")[:6],
                many=True,
            ).data,
            "risk_chart_data": [
                {"label": label, "value": value}
                for label, value in analytics.get("risk_breakdown", {}).items()
            ],
            "application_chart_data": [
                {"label": label.replace("_", " ").title(), "value": value}
                for label, value in analytics.get("application_breakdown", {}).items()
            ],
        }
        return Response(payload)


class AdminUserListAPIView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        users = CustomUser.objects.order_by("-date_joined")
        selected_role = (request.GET.get("role") or "").strip()
        search_query = (request.GET.get("q") or "").strip()
        if selected_role in {"USER", "BANK_OFFICER", "ADMIN"}:
            users = users.filter(role=selected_role)
        if search_query:
            users = users.filter(
                Q(username__icontains=search_query)
                | Q(email__icontains=search_query)
                | Q(first_name__icontains=search_query)
                | Q(last_name__icontains=search_query)
            )
        return Response(
            {
                "filters": {"role": selected_role, "q": search_query},
                "summary": {
                    "applicants_count": CustomUser.objects.filter(role="USER").count(),
                    "officers_count": CustomUser.objects.filter(
                        role="BANK_OFFICER"
                    ).count(),
                    "admins_count": CustomUser.objects.filter(role="ADMIN").count(),
                    "active_count": CustomUser.objects.filter(is_active=True).count(),
                },
                "results": UserSerializer(users, many=True).data,
            }
        )


class AdminUserUpdateAPIView(APIView):
    permission_classes = [IsPlatformAdmin]

    def patch(self, request, user_id):
        user = get_object_or_404(CustomUser, pk=user_id)
        previous_role = user.role
        previous_active = user.is_active
        serializer = AdminUserUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        _record_admin_action(
            request.user,
            "USER_ACCESS",
            (
                f"Updated {user.email or user.username}: role {previous_role} -> {user.role}, "
                f"active {previous_active} -> {user.is_active}."
            ),
        )
        return Response(UserSerializer(user).data)


class AdminOfficerListCreateAPIView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        officers = BankOfficerProfile.objects.select_related("user").order_by(
            "organization_name",
            "user__email",
        )
        return Response(
            {
                "summary": {
                    "officers_count": officers.count(),
                    "active_count": officers.filter(user__is_active=True).count(),
                    "inactive_count": officers.filter(user__is_active=False).count(),
                },
                "results": AdminOfficerSerializer(officers, many=True).data,
            }
        )

    def post(self, request):
        serializer = AdminOfficerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save()
        _record_admin_action(
            request.user,
            "OFFICER_ACCESS",
            f"Created bank officer {profile.user.email} for {profile.organization_name}.",
        )
        return Response(
            AdminOfficerSerializer(profile).data,
            status=status.HTTP_201_CREATED,
        )


class AdminOfficerDetailAPIView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request, profile_id):
        profile = get_object_or_404(BankOfficerProfile.objects.select_related("user"), pk=profile_id)
        return Response(AdminOfficerSerializer(profile).data)

    def patch(self, request, profile_id):
        profile = get_object_or_404(BankOfficerProfile.objects.select_related("user"), pk=profile_id)
        serializer = AdminOfficerUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        _record_admin_action(
            request.user,
            "OFFICER_ACCESS",
            f"Updated officer {profile.user.email or profile.user.username} for {profile.organization_name}.",
        )
        return Response(AdminOfficerSerializer(profile).data)


class AdminApplicationMonitoringAPIView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        applications = _admin_application_queryset()
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
        return Response(
            {
                "filters": {
                    "status": selected_status,
                    "risk": selected_risk,
                    "q": search_query,
                },
                "results": LoanApplicationSerializer(applications, many=True).data,
            }
        )


class AdminFraudAlertListAPIView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        alerts = FraudAlert.objects.select_related("user", "application").order_by("-detected_at")
        selected_state = (request.GET.get("state") or "").strip()
        if selected_state == "open":
            alerts = alerts.filter(resolved=False)
        elif selected_state == "resolved":
            alerts = alerts.filter(resolved=True)
        return Response(
            {
                "filters": {"state": selected_state},
                "summary": {
                    "open_count": FraudAlert.objects.filter(resolved=False).count(),
                    "resolved_count": FraudAlert.objects.filter(resolved=True).count(),
                    "critical_count": FraudAlert.objects.filter(
                        severity="CRITICAL",
                        resolved=False,
                    ).count(),
                },
                "results": FraudAlertSerializer(alerts, many=True).data,
            }
        )


class AdminFraudAlertResolveAPIView(APIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request, alert_id):
        alert = get_object_or_404(FraudAlert, pk=alert_id)
        alert.resolved = True
        alert.save(update_fields=["resolved"])
        _record_admin_action(
            request.user,
            "FRAUD_REVIEW",
            f"Marked fraud alert #{alert.id} ({alert.alert_type}) as resolved.",
        )
        return Response(FraudAlertSerializer(alert).data)


class AdminAnnouncementListCreateAPIView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        announcements = SystemAnnouncement.objects.select_related("created_by")
        return Response(
            {
                "summary": {
                    "announcement_count": announcements.count(),
                    "active_count": announcements.filter(is_active=True).count(),
                    "inactive_count": announcements.filter(is_active=False).count(),
                },
                "results": AdminAnnouncementSerializer(announcements, many=True).data,
            }
        )

    def post(self, request):
        serializer = AdminAnnouncementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        announcement = serializer.save(created_by=request.user)
        _record_admin_action(
            request.user,
            "ANNOUNCEMENT",
            f"Created announcement '{announcement.title}' for {announcement.get_audience_display().lower()}.",
        )
        return Response(
            AdminAnnouncementSerializer(announcement).data,
            status=status.HTTP_201_CREATED,
        )


class AdminAnnouncementDetailAPIView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request, announcement_id):
        announcement = get_object_or_404(SystemAnnouncement.objects.select_related("created_by"), pk=announcement_id)
        return Response(AdminAnnouncementSerializer(announcement).data)

    def patch(self, request, announcement_id):
        announcement = get_object_or_404(SystemAnnouncement.objects.select_related("created_by"), pk=announcement_id)
        previous_active = announcement.is_active
        serializer = AdminAnnouncementUpdateSerializer(
            announcement,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if "is_active" in serializer.validated_data:
            description = (
                f"{'Activated' if announcement.is_active else 'Deactivated'} announcement '{announcement.title}'."
            )
        else:
            description = f"Updated announcement '{announcement.title}'."
        _record_admin_action(request.user, "ANNOUNCEMENT", description)
        return Response(AdminAnnouncementSerializer(announcement).data)


class AdminActivityLogsAPIView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        recent_documents = FinancialProfile.objects.select_related("user").filter(
            salary_slip__isnull=False
        ).order_by("-income_proof_uploaded_at", "-updated_at")[:12]
        recent_reviews = _admin_application_queryset().exclude(reviewed_at__isnull=True)[:12]
        return Response(
            {
                "summary": {
                    "login_audit_count": LoginAudit.objects.count(),
                    "admin_action_count": AdminActionLog.objects.count(),
                    "document_count": FinancialProfile.objects.filter(
                        salary_slip__isnull=False
                    ).count(),
                    "review_count": _admin_application_queryset()
                    .exclude(reviewed_at__isnull=True)
                    .count(),
                },
                "login_audits": AdminLoginAuditSerializer(
                    LoginAudit.objects.select_related("user")[:20],
                    many=True,
                ).data,
                "admin_actions": AdminActionLogSerializer(
                    AdminActionLog.objects.select_related("actor")[:20],
                    many=True,
                ).data,
                "recent_documents": AdminFinancialDocumentSerializer(
                    recent_documents,
                    many=True,
                ).data,
                "recent_reviews": LoanApplicationSerializer(
                    recent_reviews,
                    many=True,
                ).data,
            }
        )


class AdminModelMonitoringAPIView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        snapshot = sync_latest_model_snapshot()
        analytics = build_system_analytics()
        if not snapshot:
            return Response({"detail": "Model metadata is not available yet."})
        return Response(
            {
                **_snapshot_payload(snapshot),
                "preview_features": analytics.get("preview_features", []),
                "recent_predictions": CreditPredictionSerializer(
                    CreditPrediction.objects.select_related(
                        "application",
                        "application__user",
                    )[:6],
                    many=True,
                ).data,
            }
        )


class AdminAnalyticsAPIView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        analytics = build_system_analytics()
        snapshot = analytics.get("latest_snapshot")
        return Response(
            {
                **analytics,
                "latest_snapshot": _snapshot_payload(snapshot),
                "risk_chart_data": [
                    {"label": label, "value": value}
                    for label, value in analytics.get("risk_breakdown", {}).items()
                ],
                "application_chart_data": [
                    {"label": label.replace("_", " ").title(), "value": value}
                    for label, value in analytics.get("application_breakdown", {}).items()
                ],
            }
        )


class AdminSystemAnalyticsAPIView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        analytics = build_system_analytics()
        snapshot = analytics.get("latest_snapshot")
        analytics["latest_snapshot"] = _snapshot_payload(snapshot)
        return Response(analytics)
