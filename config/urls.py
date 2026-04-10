"""Root URL configuration for CreditSense AI."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from authentication.views import admin_login_view

urlpatterns = [
    path("admin/login/", admin_login_view, name="admin-login-direct"),
    path("admin/", include("admin_panel.urls")),
    path("django-admin/", admin.site.urls),
    path("", include("authentication.urls")),
    path("user/", include("users.urls")),
    path("credit/", include("credit_prediction.urls")),
    path("recommendations/", include("recommendations.urls")),
    path("officer/", include("bank_officer.urls")),
    path("analytics/", include("analytics.urls")),
    path("api/", include("api.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
