from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError


class HeadphoneStatus(models.TextChoices):
    PENDING_BORROW = 'pending_borrow', '待领出'
    IN_USE = 'in_use', '使用中'
    PENDING_DISINFECT = 'pending_disinfect', '待消杀'
    PENDING_REVIEW = 'pending_review', '待复核'
    AVAILABLE = 'available', '恢复可用'
    OUT_OF_SERVICE = 'out_of_service', '停用观察'


class UserRole(models.TextChoices):
    ADMIN = 'admin', '管理员'
    FIELD_STAFF = 'field_staff', '现场人员'


class Batch(models.Model):
    batch_no = models.CharField('批次编号', max_length=50, unique=True)
    name = models.CharField('批次名称', max_length=100)
    purchase_date = models.DateField('采购日期', null=True, blank=True)
    total_quantity = models.IntegerField('总数量', default=0)
    remark = models.TextField('备注', blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '批次'
        verbose_name_plural = '批次'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.batch_no} - {self.name}'


class Box(models.Model):
    box_no = models.CharField('盒位编号', max_length=50, unique=True)
    location = models.CharField('存放位置', max_length=200, blank=True)
    capacity = models.IntegerField('容量', default=1)
    remark = models.TextField('备注', blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '存放盒位'
        verbose_name_plural = '存放盒位'
        ordering = ['box_no']

    def __str__(self):
        return self.box_no

    def get_pending_review_count(self):
        return Headphone.objects.filter(
            box=self,
            status=HeadphoneStatus.PENDING_REVIEW
        ).count()


class Headphone(models.Model):
    serial_no = models.CharField('耳机编号', max_length=50, unique=True)
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, verbose_name='所属批次',
                              related_name='headphones')
    box = models.ForeignKey(Box, on_delete=models.PROTECT, verbose_name='存放盒位',
                            related_name='headphones', null=True, blank=True)
    compatible_terminal = models.CharField('适配终端', max_length=100, blank=True)
    responsible_person = models.CharField('责任人', max_length=50, blank=True)
    status = models.CharField('状态', max_length=20,
                              choices=HeadphoneStatus.choices,
                              default=HeadphoneStatus.PENDING_BORROW)
    battery_level = models.IntegerField('电量(%)', default=100)
    earpad_damaged = models.BooleanField('耳罩破损', default=False)
    last_borrow_time = models.DateTimeField('上次领出时间', null=True, blank=True)
    last_return_time = models.DateTimeField('上次归还时间', null=True, blank=True)
    current_borrower = models.CharField('当前领用人', max_length=50, blank=True)
    suspend_reason = models.TextField('停用说明', blank=True)
    remark = models.TextField('备注', blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '耳机'
        verbose_name_plural = '耳机'
        ordering = ['serial_no']

    def __str__(self):
        return self.serial_no

    def clean(self):
        if self.status == HeadphoneStatus.PENDING_REVIEW and self.box:
            pending_count = Headphone.objects.filter(
                box=self.box,
                status=HeadphoneStatus.PENDING_REVIEW
            ).exclude(pk=self.pk).count()
            if pending_count >= self.box.capacity:
                raise ValidationError(f'盒位 {self.box.box_no} 已被待复核耳机占用')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def can_borrow(self):
        return self.status in [HeadphoneStatus.PENDING_BORROW, HeadphoneStatus.AVAILABLE]

    def can_return(self):
        return self.status == HeadphoneStatus.IN_USE

    def can_disinfect(self):
        return self.status == HeadphoneStatus.PENDING_DISINFECT

    def can_review(self):
        return self.status == HeadphoneStatus.PENDING_REVIEW


class BorrowRecord(models.Model):
    headphone = models.ForeignKey(Headphone, on_delete=models.CASCADE,
                                  verbose_name='耳机', related_name='borrow_records')
    borrower = models.CharField('领用人', max_length=50)
    borrow_time = models.DateTimeField('领出时间', auto_now_add=True)
    expected_return_time = models.DateTimeField('预计归还时间', null=True, blank=True)
    original_expected_return_time = models.DateTimeField('原始预计归还时间', null=True, blank=True)
    return_time = models.DateTimeField('归还时间', null=True, blank=True)
    battery_before = models.IntegerField('领出前电量(%)', null=True, blank=True)
    battery_after = models.IntegerField('归还时电量(%)', null=True, blank=True)
    earpad_damaged_before = models.BooleanField('领出前耳罩破损', default=False)
    earpad_damaged_after = models.BooleanField('归还时耳罩破损', default=False)
    terminal_used = models.CharField('使用终端', max_length=100, blank=True)
    return_remark = models.TextField('归还备注', blank=True)
    operator_borrow = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                        verbose_name='登记人(领出)',
                                        related_name='borrow_operations')
    operator_return = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                        verbose_name='登记人(归还)',
                                        related_name='return_operations')
    is_overdue = models.BooleanField('是否超时', default=False)

    class Meta:
        verbose_name = '领用记录'
        verbose_name_plural = '领用记录'
        ordering = ['-borrow_time']

    def __str__(self):
        return f'{self.headphone.serial_no} - {self.borrower}'

    def check_overdue(self):
        if self.return_time or not self.expected_return_time:
            return False
        approved_extension = self.extension_applies.filter(
            status=ExtensionApplyStatus.APPROVED
        ).order_by('-apply_time').first()
        effective_return_time = approved_extension.approved_new_return_time if approved_extension else self.expected_return_time
        return timezone.now() > effective_return_time

    def get_effective_expected_return_time(self):
        approved_extension = self.extension_applies.filter(
            status=ExtensionApplyStatus.APPROVED
        ).order_by('-apply_time').first()
        if approved_extension:
            return approved_extension.approved_new_return_time
        return self.expected_return_time

    def has_pending_extension(self):
        return self.extension_applies.filter(
            status=ExtensionApplyStatus.PENDING
        ).exists()

    def is_extended(self):
        return self.extension_applies.filter(
            status=ExtensionApplyStatus.APPROVED
        ).exists()


class ExtensionApplyStatus(models.TextChoices):
    PENDING = 'pending', '待审批'
    APPROVED = 'approved', '已通过'
    REJECTED = 'rejected', '已驳回'


class ExtensionApply(models.Model):
    borrow_record = models.ForeignKey(BorrowRecord, on_delete=models.CASCADE,
                                      verbose_name='领用记录', related_name='extension_applies')
    headphone = models.ForeignKey(Headphone, on_delete=models.CASCADE,
                                  verbose_name='耳机', related_name='extension_applies')
    applicant = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                  verbose_name='申请人', related_name='extension_applies')
    applicant_name = models.CharField('申请人姓名', max_length=50, blank=True)
    apply_time = models.DateTimeField('申请时间', auto_now_add=True)
    original_expected_return_time = models.DateTimeField('原预计归还时间')
    extension_hours = models.IntegerField('延期时长(小时)')
    requested_new_return_time = models.DateTimeField('申请的新预计归还时间')
    approved_new_return_time = models.DateTimeField('审批通过的新预计归还时间', null=True, blank=True)
    reason = models.TextField('延期原因')
    status = models.CharField('申请状态', max_length=20,
                              choices=ExtensionApplyStatus.choices,
                              default=ExtensionApplyStatus.PENDING)
    approver = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                 verbose_name='审批人', related_name='approved_extensions')
    approver_name = models.CharField('审批人姓名', max_length=50, blank=True)
    approve_time = models.DateTimeField('审批时间', null=True, blank=True)
    approve_remark = models.TextField('审批备注', blank=True)

    class Meta:
        verbose_name = '归还延期申请'
        verbose_name_plural = '归还延期申请'
        ordering = ['-apply_time']

    def __str__(self):
        return f'{self.headphone.serial_no} - {self.applicant_name} - {self.get_status_display()}'


class DisinfectionRecord(models.Model):
    headphone = models.ForeignKey(Headphone, on_delete=models.CASCADE,
                                  verbose_name='耳机', related_name='disinfection_records')
    operator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                 verbose_name='消杀操作人')
    disinfect_time = models.DateTimeField('消杀时间', auto_now_add=True)
    disinfect_method = models.CharField('消杀方式', max_length=100, default='酒精擦拭')
    result = models.BooleanField('消杀结果', default=True)
    remark = models.TextField('备注', blank=True)

    class Meta:
        verbose_name = '消杀记录'
        verbose_name_plural = '消杀记录'
        ordering = ['-disinfect_time']

    def __str__(self):
        return f'{self.headphone.serial_no} - {self.disinfect_time}'


class ReviewRecord(models.Model):
    headphone = models.ForeignKey(Headphone, on_delete=models.CASCADE,
                                  verbose_name='耳机', related_name='review_records')
    reviewer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                 verbose_name='复核人')
    review_time = models.DateTimeField('复核时间', auto_now_add=True)
    passed = models.BooleanField('复核通过', default=True)
    earpad_damaged = models.BooleanField('耳罩破损', default=False)
    battery_ok = models.BooleanField('电量正常', default=True)
    appearance_ok = models.BooleanField('外观正常', default=True)
    function_ok = models.BooleanField('功能正常', default=True)
    remark = models.TextField('复核备注', blank=True)

    class Meta:
        verbose_name = '复核记录'
        verbose_name_plural = '复核记录'
        ordering = ['-review_time']

    def __str__(self):
        return f'{self.headphone.serial_no} - {self.review_time}'


class AbnormalStatus(models.TextChoices):
    PENDING = 'pending', '未处理'
    PROCESSING = 'processing', '处理中'
    RESOLVED = 'resolved', '已处理'


class AbnormalRecord(models.Model):
    ABNORMAL_TYPES = (
        ('low_battery', '连续低电量'),
        ('earpad_damage', '同批次耳罩破损偏多'),
        ('overdue', '归还超时'),
        ('review_missed', '复核遗漏'),
        ('terminal_conflict', '终端适配冲突'),
    )

    SEVERITY = (
        ('low', '低'),
        ('medium', '中'),
        ('high', '高'),
    )

    headphone = models.ForeignKey(Headphone, on_delete=models.CASCADE,
                                  verbose_name='耳机', related_name='abnormal_records',
                                  null=True, blank=True)
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE,
                              verbose_name='批次', related_name='abnormal_records',
                              null=True, blank=True)
    abnormal_type = models.CharField('异常类型', max_length=30, choices=ABNORMAL_TYPES)
    severity = models.CharField('严重程度', max_length=20, choices=SEVERITY, default='medium')
    description = models.TextField('异常描述')
    detected_time = models.DateTimeField('检测时间', auto_now_add=True)
    status = models.CharField('处理状态', max_length=20,
                              choices=AbnormalStatus.choices,
                              default=AbnormalStatus.PENDING)
    handler = models.ForeignKey(User, on_delete=models.SET_NULL,
                                verbose_name='处理人',
                                related_name='handled_abnormal_records',
                                null=True, blank=True)
    handle_time = models.DateTimeField('处理时间', null=True, blank=True)
    resolve_remark = models.TextField('处理备注', blank=True)

    class Meta:
        verbose_name = '异常记录'
        verbose_name_plural = '异常记录'
        ordering = ['-detected_time']

    def __str__(self):
        return f'{self.get_abnormal_type_display()} - {self.detected_time}'

    @property
    def resolved(self):
        return self.status == AbnormalStatus.RESOLVED


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField('角色', max_length=20, choices=UserRole.choices,
                            default=UserRole.FIELD_STAFF)
    phone = models.CharField('联系电话', max_length=20, blank=True)
    department = models.CharField('部门', max_length=100, blank=True)

    class Meta:
        verbose_name = '用户资料'
        verbose_name_plural = '用户资料'

    def __str__(self):
        return f'{self.user.username} - {self.get_role_display()}'

    def is_admin(self):
        return self.role == UserRole.ADMIN
