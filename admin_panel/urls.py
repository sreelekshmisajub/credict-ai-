from django.urls import path

from . import views

app_name = "admin_panel"

urlpatterns = [
    path("", views.admin_entry, name="entry"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("users/", views.user_management, name="user-management"),
    path("officers/", views.officer_management, name="officer-management"),
    path("applications/", views.application_monitoring, name="application-monitoring"),
    path("model-monitoring/", views.model_monitoring, name="model-monitoring"),
    path("fraud-monitoring/", views.fraud_monitoring, name="fraud-monitoring"),
    path("analytics/", views.analytics_view, name="analytics"),
    path("announcements/", views.announcements, name="announcements"),
    path("activity-logs/", views.activity_logs, name="activity-logs"),
    path("risk-analysis/", views.risk_analysis, name="risk-analysis"),
    path("document-verification/", views.document_verification, name="document-verification"),
    path("risk-configuration/", views.risk_configuration, name="risk-configuration"),
    path("settings/", views.system_settings, name="settings"),
]
