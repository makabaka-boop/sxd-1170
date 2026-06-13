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
        return timezone.now() > self.expected_return_time


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
    resolved = models.BooleanField('已处理', default=False)
    resolve_remark = models.TextField('处理备注', blank=True)

    class Meta:
        verbose_name = '异常记录'
        verbose_name_plural = '异常记录'
        ordering = ['-detected_time']

    def __str__(self):
        return f'{self.get_abnormal_type_display()} - {self.detected_time}'


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
