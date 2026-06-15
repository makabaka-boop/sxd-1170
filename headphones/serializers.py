from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    Batch, Box, Headphone, BorrowRecord, DisinfectionRecord,
    ReviewRecord, AbnormalRecord, UserProfile, HeadphoneStatus,
    ExtensionApply, ExtensionApplyStatus
)


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['role', 'phone', 'department']


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)
    role = serializers.CharField(source='profile.role', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'profile', 'role']


class BatchSerializer(serializers.ModelSerializer):
    headphone_count = serializers.SerializerMethodField()

    class Meta:
        model = Batch
        fields = '__all__'

    def get_headphone_count(self, obj):
        return obj.headphones.count()


class BoxSerializer(serializers.ModelSerializer):
    pending_review_count = serializers.SerializerMethodField()

    class Meta:
        model = Box
        fields = '__all__'

    def get_pending_review_count(self, obj):
        return obj.get_pending_review_count()


class ExtensionApplySerializer(serializers.ModelSerializer):
    headphone_serial = serializers.CharField(source='headphone.serial_no', read_only=True)
    borrower = serializers.CharField(source='borrow_record.borrower', read_only=True)
    borrow_record_id = serializers.IntegerField(source='borrow_record.id', read_only=True)
    applicant_username = serializers.CharField(source='applicant.username', read_only=True, allow_null=True)
    approver_username = serializers.CharField(source='approver.username', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ExtensionApply
        fields = '__all__'
        read_only_fields = [
            'apply_time', 'applicant', 'applicant_name',
            'original_expected_return_time', 'requested_new_return_time',
            'approved_new_return_time', 'status', 'approver',
            'approver_name', 'approve_time', 'headphone', 'borrow_record'
        ]


class ExtensionApplyCreateSerializer(serializers.Serializer):
    borrow_record_id = serializers.IntegerField()
    extension_hours = serializers.IntegerField(min_value=1)
    reason = serializers.CharField()


class ExtensionApplyApproveSerializer(serializers.Serializer):
    approved = serializers.BooleanField()
    approve_remark = serializers.CharField(required=False, allow_blank=True)
    extension_hours = serializers.IntegerField(required=False, min_value=1)


class HeadphoneSerializer(serializers.ModelSerializer):
    batch_info = serializers.SerializerMethodField()
    box_info = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    extension_applies = serializers.SerializerMethodField()
    current_extension = serializers.SerializerMethodField()

    class Meta:
        model = Headphone
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']

    def get_batch_info(self, obj):
        if obj.batch:
            return {'id': obj.batch.id, 'batch_no': obj.batch.batch_no, 'name': obj.batch.name}
        return None

    def get_box_info(self, obj):
        if obj.box:
            return {'id': obj.box.id, 'box_no': obj.box.box_no, 'location': obj.box.location}
        return None

    def get_extension_applies(self, obj):
        applies = obj.extension_applies.all()[:10]
        return ExtensionApplySerializer(applies, many=True).data

    def get_current_extension(self, obj):
        latest_approved = obj.extension_applies.filter(
            status=ExtensionApplyStatus.APPROVED,
            borrow_record__return_time__isnull=True
        ).order_by('-apply_time').first()
        if latest_approved:
            return ExtensionApplySerializer(latest_approved).data
        pending = obj.extension_applies.filter(
            status=ExtensionApplyStatus.PENDING,
            borrow_record__return_time__isnull=True
        ).order_by('-apply_time').first()
        if pending:
            return ExtensionApplySerializer(pending).data
        return None


class HeadphoneListSerializer(serializers.ModelSerializer):
    batch_no = serializers.CharField(source='batch.batch_no', read_only=True)
    box_no = serializers.CharField(source='box.box_no', read_only=True, allow_null=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    has_extension = serializers.SerializerMethodField()

    class Meta:
        model = Headphone
        fields = [
            'id', 'serial_no', 'batch', 'batch_no', 'box', 'box_no',
            'compatible_terminal', 'responsible_person', 'status', 'status_display',
            'battery_level', 'earpad_damaged', 'current_borrower',
            'last_borrow_time', 'last_return_time', 'has_extension'
        ]

    def get_has_extension(self, obj):
        return obj.extension_applies.filter(
            borrow_record__return_time__isnull=True
        ).exists()


class BorrowRecordSerializer(serializers.ModelSerializer):
    headphone_serial = serializers.CharField(source='headphone.serial_no', read_only=True)
    operator_borrow_name = serializers.CharField(source='operator_borrow.username', read_only=True)
    operator_return_name = serializers.CharField(source='operator_return.username', read_only=True)
    extension_applies = serializers.SerializerMethodField()
    latest_extension = serializers.SerializerMethodField()
    effective_expected_return_time = serializers.SerializerMethodField()
    is_extended = serializers.SerializerMethodField()
    has_pending_extension = serializers.SerializerMethodField()

    class Meta:
        model = BorrowRecord
        fields = '__all__'
        read_only_fields = ['borrow_time', 'operator_borrow', 'original_expected_return_time']

    def get_extension_applies(self, obj):
        applies = obj.extension_applies.all()
        return ExtensionApplySerializer(applies, many=True).data

    def get_latest_extension(self, obj):
        latest = obj.extension_applies.order_by('-apply_time').first()
        if latest:
            return ExtensionApplySerializer(latest).data
        return None

    def get_effective_expected_return_time(self, obj):
        return obj.get_effective_expected_return_time()

    def get_is_extended(self, obj):
        return obj.is_extended()

    def get_has_pending_extension(self, obj):
        return obj.has_pending_extension()


class DisinfectionRecordSerializer(serializers.ModelSerializer):
    headphone_serial = serializers.CharField(source='headphone.serial_no', read_only=True)
    operator_name = serializers.CharField(source='operator.username', read_only=True)

    class Meta:
        model = DisinfectionRecord
        fields = '__all__'
        read_only_fields = ['disinfect_time', 'operator']


class ReviewRecordSerializer(serializers.ModelSerializer):
    headphone_serial = serializers.CharField(source='headphone.serial_no', read_only=True)
    reviewer_name = serializers.CharField(source='reviewer.username', read_only=True)

    class Meta:
        model = ReviewRecord
        fields = '__all__'
        read_only_fields = ['review_time', 'reviewer']


class AbnormalRecordSerializer(serializers.ModelSerializer):
    headphone_serial = serializers.CharField(source='headphone.serial_no', read_only=True, allow_null=True)
    batch_no = serializers.CharField(source='batch.batch_no', read_only=True, allow_null=True)
    abnormal_type_display = serializers.CharField(source='get_abnormal_type_display', read_only=True)
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    handler_name = serializers.CharField(source='handler.username', read_only=True, allow_null=True)

    class Meta:
        model = AbnormalRecord
        fields = '__all__'
        read_only_fields = ['detected_time', 'handler', 'handle_time']


class BorrowActionSerializer(serializers.Serializer):
    headphone_id = serializers.IntegerField()
    borrower = serializers.CharField(max_length=50)
    expected_return_hours = serializers.IntegerField(required=False, default=8)
    terminal_used = serializers.CharField(max_length=100, required=False, allow_blank=True)


class ReturnActionSerializer(serializers.Serializer):
    headphone_id = serializers.IntegerField()
    battery_after = serializers.IntegerField(min_value=0, max_value=100)
    earpad_damaged_after = serializers.BooleanField(default=False)
    return_remark = serializers.CharField(required=False, allow_blank=True)


class DisinfectActionSerializer(serializers.Serializer):
    headphone_id = serializers.IntegerField()
    disinfect_method = serializers.CharField(max_length=100, default='酒精擦拭')
    result = serializers.BooleanField(default=True)
    remark = serializers.CharField(required=False, allow_blank=True)


class ReviewActionSerializer(serializers.Serializer):
    headphone_id = serializers.IntegerField()
    passed = serializers.BooleanField(default=True)
    earpad_damaged = serializers.BooleanField(default=False)
    battery_ok = serializers.BooleanField(default=True)
    appearance_ok = serializers.BooleanField(default=True)
    function_ok = serializers.BooleanField(default=True)
    remark = serializers.CharField(required=False, allow_blank=True)


class SuspendActionSerializer(serializers.Serializer):
    headphone_id = serializers.IntegerField()
    reason = serializers.CharField()


class AbnormalHandleSerializer(serializers.Serializer):
    remark = serializers.CharField(required=False, allow_blank=True)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()
