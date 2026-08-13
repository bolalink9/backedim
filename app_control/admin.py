from django.contrib import admin
from .models import AppRule, DailyUsageSummary


@admin.register(AppRule)
class AppRuleAdmin(admin.ModelAdmin):
    list_display  = ('child', 'package_name', 'app_label', 'is_blocked', 'daily_limit_mins', 'updated_at')
    list_filter   = ('is_blocked', 'family')
    search_fields = ('package_name', 'app_label', 'child__full_name')


@admin.register(DailyUsageSummary)
class DailyUsageSummaryAdmin(admin.ModelAdmin):
    list_display  = ('child', 'package_name', 'app_label', 'total_mins', 'date')
    list_filter   = ('date', 'family')
    search_fields = ('package_name', 'child__full_name')
