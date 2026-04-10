from django.shortcuts import render

from authentication.decorators import role_required

from .services import build_system_analytics


@role_required("ADMIN", "BANK_OFFICER")
def overview(request):
    return render(request, "analytics/overview.html", {"analytics": build_system_analytics()})
