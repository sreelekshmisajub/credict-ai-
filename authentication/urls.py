from django.urls import path

from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("dashboard/", views.dashboard_router, name="dashboard-router"),
    path("login/", views.login_view, name="login"),
    path("admin/login/", views.admin_login_view, name="admin-login-alias"),
    path("admin-login/", views.admin_login_view, name="admin-login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
]
