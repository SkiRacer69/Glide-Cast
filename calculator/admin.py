from django.contrib import admin

from .models import CalculationAuditLog, CalculationHistory


@admin.register(CalculationHistory)
class CalculationHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at",)


@admin.register(CalculationAuditLog)
class CalculationAuditLogAdmin(admin.ModelAdmin):
    list_display = ("user", "plan_tier", "created_at")
    list_filter = ("plan_tier", "created_at")
    search_fields = ("user__username",)
    readonly_fields = ("created_at",)
