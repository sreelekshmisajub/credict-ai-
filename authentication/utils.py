def dashboard_route_name(user):
    if user.role == "ADMIN":
        return "admin_panel:dashboard"
    if user.role == "BANK_OFFICER":
        return "bank_officer:dashboard"
    return "users:dashboard"
