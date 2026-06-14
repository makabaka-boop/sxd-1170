from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import (
    Batch, Box, Headphone, BorrowRecord, DisinfectionRecord,
    ReviewRecord, AbnormalRecord, UserProfile
)


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = '用户资料'


class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_role')

    def get_role(self, obj):
        return obj.profile.get_role_display() if hasattr(obj, 'profile') else '-'
    get_role.short_description = '角色'


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ('batch_no', 'name', 'purchase_date', 'total_quantity', 'created_at')
    search_fields = ('batch_no', 'name')
    list_filter = ('purchase_date',)
    ordering = ('-created_at',)


@admin.register(Box)
class BoxAdmin(admin.ModelAdmin):
    list_display = ('box_no', 'location', 'capacity', 'get_pending_count')
    search_fields = ('box_no', 'location')
    ordering = ('box_no',)

    def get_pending_count(self, obj):
        return obj.get_pending_review_count()
    get_pending_count.short_description = '待复核数量'


@admin.register(Headphone)
class HeadphoneAdmin(admin.ModelAdmin):
    list_display = (
        'serial_no', 'batch', 'box', 'status', 'battery_level',
        'earpad_damaged', 'responsible_person', 'current_borrower'
    )
    search_fields = ('serial_no', 'responsible_person', 'compatible_terminal')
    list_filter = ('status', 'earpad_damaged', 'batch', 'box')
    ordering = ('serial_no',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(BorrowRecord)
class BorrowRecordAdmin(admin.ModelAdmin):
    list_display = (
        'headphone', 'borrower', 'borrow_time', 'expected_return_time',
        'return_time', 'is_overdue', 'operator_borrow'
    )
    search_fields = ('headphone__serial_no', 'borrower')
    list_filter = ('is_overdue', 'borrow_time')
    ordering = ('-borrow_time',)
    readonly_fields = ('borrow_time',)


@admin.register(DisinfectionRecord)
class DisinfectionRecordAdmin(admin.ModelAdmin):
    list_display = ('headphone', 'disinfect_time', 'operator', 'result', 'disinfect_method')
    search_fields = ('headphone__serial_no',)
    list_filter = ('result', 'disinfect_time')
    ordering = ('-disinfect_time',)
    readonly_fields = ('disinfect_time',)


@admin.register(ReviewRecord)
class ReviewRecordAdmin(admin.ModelAdmin):
    list_display = (
        'headphone', 'review_time', 'reviewer', 'passed',
        'earpad_damaged', 'battery_ok', 'appearance_ok', 'function_ok'
    )
    search_fields = ('headphone__serial_no',)
    list_filter = ('passed', 'review_time')
    ordering = ('-review_time',)
    readonly_fields = ('review_time',)


@admin.register(AbnormalRecord)
class AbnormalRecordAdmin(admin.ModelAdmin):
    list_display = (
        'abnormal_type', 'severity', 'headphone', 'batch',
        'detected_time', 'status', 'handler', 'handle_time'
    )
    search_fields = ('description', 'headphone__serial_no', 'handler__username')
    list_filter = ('abnormal_type', 'severity', 'status', 'detected_time', 'handle_time')
    ordering = ('-detected_time',)
    readonly_fields = ('detected_time', 'handler', 'handle_time')
    fieldsets = (
        (None, {
            'fields': ('abnormal_type', 'severity', 'headphone', 'batch', 'description', 'detected_time')
        }),
        ('处理信息', {
            'fields': ('status', 'handler', 'handle_time', 'resolve_remark')
        }),
    )


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
