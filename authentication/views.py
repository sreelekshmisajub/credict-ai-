import json

from django.contrib import messages
from django.contrib.auth import login, logout
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from analytics.services import build_system_analytics

from .forms import (
    LoginForm,
    RegisterForm,
    build_employment_document_ui_config,
)
from .models import LoginAudit
from .utils import dashboard_route_name


def _client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def landing(request):
    if request.user.is_authenticated:
        return redirect(dashboard_route_name(request.user))
    return render(request, "auth/landing.html", {"stats": build_system_analytics()})


def dashboard_router(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return redirect(dashboard_route_name(request.user))


def login_view(request):
    if request.user.is_authenticated:
        return redirect(dashboard_route_name(request.user))

    form = LoginForm(request, request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            LoginAudit.objects.create(
                user=user,
                username_attempt=user.username,
                successful=True,
                ip_address=_client_ip(request),
            )
            messages.success(request, f"Welcome back, {user.first_name or user.username}.")
            return redirect(dashboard_route_name(user))

        LoginAudit.objects.create(
            username_attempt=request.POST.get("email", ""),
            successful=False,
            ip_address=_client_ip(request),
        )
        messages.error(request, "Invalid email or password. Please try again.")

    return render(
        request,
        "auth/login.html",
        {
            "form": form,
            "page_title": "Sign in",
            "page_description": "Access your CreditSense AI dashboard to manage applications and view credit insights.",
        },
    )


def register_view(request):
    if request.user.is_authenticated:
        return redirect(dashboard_route_name(request.user))

    form = RegisterForm(request.POST or None, request.FILES or None)
    wants_json = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
    )
    if request.method == "POST":
        if form.is_valid():
            user = form.save()
            if wants_json:
                return JsonResponse(
                    {
                        "success": True,
                        "redirect_url": reverse("login"),
                        "user_id": user.id,
                    }
                )
            messages.success(
                request,
                "Registration successful. Please login to continue.",
            )
            return redirect("login")
        if wants_json:
            missing_document_fields = form.cleaned_data.get("missing_document_fields", [])
            if missing_document_fields:
                return JsonResponse(
                    {
                        "error": "missing_documents",
                        "fields": missing_document_fields,
                    },
                    status=400,
                )
            return JsonResponse(
                {
                    "error": "validation_error",
                    "fields": form.errors.get_json_data(),
                },
                status=400,
            )
        messages.error(request, "Please correct the errors below.")
            
    return render(
        request,
        "auth/register.html",
        {
            "form": form,
            "employment_document_requirements_json": build_employment_document_ui_config(),
        },
    )


def admin_login_view(request):
    return redirect("login")


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("landing")
