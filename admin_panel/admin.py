from django.contrib import admin

from .models import AdminProfile, SystemAnnouncement


@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "department", "can_manage_models", "created_at")
    search_fields = ("user__username", "user__email", "department")


@admin.register(SystemAnnouncement)
class SystemAnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "audience", "is_active", "created_by", "created_at")
    list_filter = ("audience", "is_active")
    search_fields = ("title", "message", "created_by__username", "created_by__email")
