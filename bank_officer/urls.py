from django.urls import path

from . import views

app_name = "bank_officer"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("applications/", views.applications, name="applications"),
    path(
        "applications/<int:application_id>/",
        views.application_detail,
        name="application-detail",
    ),
    path("risk-analysis/", views.risk_analysis, name="risk-analysis"),
    path(
        "risk-analysis/<int:application_id>/",
        views.risk_analysis_detail,
        name="risk-analysis-detail",
    ),
    path("explanations/", views.explanations, name="explanations"),
    path(
        "explanations/<int:application_id>/",
        views.explanation_detail,
        name="explanation-detail",
    ),
    path("decision/<int:application_id>/", views.decision, name="decision"),
    path("applicant/<int:user_id>/", views.applicant_profile, name="applicant-profile"),
    path("fraud-alerts/", views.fraud_alerts, name="fraud-alerts"),
    path("reports/", views.reports, name="reports"),
    path("notifications/", views.notifications, name="notifications"),
    path("profile/", views.profile, name="profile"),
    path(
        "document-verification/",
        views.document_verification,
        name="document_verification",
    ),
]
