from django.urls import path

from . import views

app_name = "users"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("financial-data/", views.financial_data, name="financial-data"),
    path("credit-score/", views.credit_score, name="credit-score"),
    path("explanation/", views.explanation, name="explanation"),
    path("improvements/", views.improvements, name="improvements"),
    path("history/", views.history, name="history"),
    path("fraud-alerts/", views.fraud_alerts, name="fraud-alerts"),
    path("profile/", views.profile, name="profile"),
    path("documents/", views.documents, name="documents"),
    path("notifications/", views.notifications, name="notifications"),
]
