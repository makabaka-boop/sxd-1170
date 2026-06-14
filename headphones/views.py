from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.utils import timezone
from django.db import transaction, IntegrityError
from django.db.models import Count, Q, Avg, F
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from datetime import timedelta

from .models import (
    Batch, Box, Headphone, BorrowRecord, DisinfectionRecord,
    ReviewRecord, AbnormalRecord, UserProfile, HeadphoneStatus,
    UserRole, AbnormalStatus
)
from .serializers import (
    BatchSerializer, BoxSerializer, HeadphoneSerializer, HeadphoneListSerializer,
    BorrowRecordSerializer, DisinfectionRecordSerializer, ReviewRecordSerializer,
    AbnormalRecordSerializer, AbnormalHandleSerializer,
    BorrowActionSerializer, ReturnActionSerializer,
    DisinfectActionSerializer, ReviewActionSerializer, SuspendActionSerializer,
    UserSerializer, LoginSerializer
)
from .filters import (
    HeadphoneFilter, BorrowRecordFilter, AbnormalRecordFilter,
    DisinfectionRecordFilter, ReviewRecordFilter
)


def _is_user_admin(user):
    try:
        return user.profile.is_admin()
    except (ObjectDoesNotExist, AttributeError):
        return False


class IsAdminOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return _is_user_admin(request.user)


class BatchViewSet(viewsets.ModelViewSet):
    queryset = Batch.objects.all()
    serializer_class = BatchSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]
    search_fields = ['batch_no', 'name']
    ordering_fields = ['created_at', 'batch_no']


class BoxViewSet(viewsets.ModelViewSet):
    queryset = Box.objects.all()
    serializer_class = BoxSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]
    search_fields = ['box_no', 'location']
    ordering_fields = ['box_no']


class HeadphoneViewSet(viewsets.ModelViewSet):
    queryset = Headphone.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    filterset_class = HeadphoneFilter
    search_fields = ['serial_no', 'responsible_person', 'compatible_terminal']
    ordering_fields = ['serial_no', 'battery_level', 'created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return HeadphoneListSerializer
        return HeadphoneSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsAdminOrReadOnly()]
        return [permissions.IsAuthenticated()]


class BorrowRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BorrowRecord.objects.all()
    serializer_class = BorrowRecordSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_class = BorrowRecordFilter
    search_fields = ['borrower', 'headphone__serial_no']
    ordering_fields = ['borrow_time', 'return_time']


class DisinfectionRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DisinfectionRecord.objects.all()
    serializer_class = DisinfectionRecordSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_class = DisinfectionRecordFilter
    search_fields = ['headphone__serial_no']
    ordering_fields = ['disinfect_time']


class ReviewRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ReviewRecord.objects.all()
    serializer_class = ReviewRecordSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_class = ReviewRecordFilter
    search_fields = ['headphone__serial_no']
    ordering_fields = ['review_time']


class AbnormalRecordViewSet(viewsets.ModelViewSet):
    queryset = AbnormalRecord.objects.all()
    serializer_class = AbnormalRecordSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_class = AbnormalRecordFilter
    search_fields = ['description']
    ordering_fields = ['detected_time', 'severity', 'handle_time']

    def get_permissions(self):
        if self.action in ['create', 'destroy', 'confirm', 'resolve']:
            return [permissions.IsAuthenticated(), IsAdminOrReadOnly()]
        return [permissions.IsAuthenticated()]

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        abnormal = self.get_object()
        if abnormal.status != AbnormalStatus.PENDING:
            return Response(
                {'error': '只有未处理的异常才能确认'},
                status=status.HTTP_400_BAD_REQUEST
            )
        serializer = AbnormalHandleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        abnormal.status = AbnormalStatus.PROCESSING
        abnormal.handler = request.user
        abnormal.resolve_remark = data.get('remark', '')
        abnormal.save()

        result = AbnormalRecordSerializer(abnormal).data
        return Response(result, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        abnormal = self.get_object()
        if abnormal.status == AbnormalStatus.RESOLVED:
            return Response(
                {'error': '该异常已处理完成'},
                status=status.HTTP_400_BAD_REQUEST
            )
        serializer = AbnormalHandleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        abnormal.status = AbnormalStatus.RESOLVED
        abnormal.handler = request.user
        abnormal.handle_time = timezone.now()
        abnormal.resolve_remark = data.get('remark', abnormal.resolve_remark)
        abnormal.save()

        result = AbnormalRecordSerializer(abnormal).data
        return Response(result, status=status.HTTP_200_OK)


class HeadphoneActionView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    LOW_BATTERY_THRESHOLD = 30
    CONSECUTIVE_LOW_BATTERY_COUNT = 3

    @action(detail=False, methods=['post'])
    def post(self, request, action_type=None):
        if action_type == 'borrow':
            return self._borrow(request)
        elif action_type == 'return':
            return self._return(request)
        elif action_type == 'disinfect':
            return self._disinfect(request)
        elif action_type == 'review':
            return self._review(request)
        elif action_type == 'suspend':
            return self._suspend(request)
        elif action_type == 'activate':
            return self._activate(request)
        return Response({'error': '未知操作类型'}, status=status.HTTP_400_BAD_REQUEST)

    @transaction.atomic
    def _borrow(self, request):
        serializer = BorrowActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            headphone = Headphone.objects.select_for_update().get(pk=data['headphone_id'])
        except Headphone.DoesNotExist:
            return Response({'error': '耳机不存在'}, status=status.HTTP_404_NOT_FOUND)

        if not headphone.can_borrow():
            return Response(
                {'error': f'耳机当前状态为 {headphone.get_status_display()}，无法领出'},
                status=status.HTTP_400_BAD_REQUEST
            )

        expected_return = timezone.now() + timedelta(hours=data.get('expected_return_hours', 8))

        borrow_record = BorrowRecord.objects.create(
            headphone=headphone,
            borrower=data['borrower'],
            expected_return_time=expected_return,
            battery_before=headphone.battery_level,
            earpad_damaged_before=headphone.earpad_damaged,
            terminal_used=data.get('terminal_used', ''),
            operator_borrow=request.user
        )

        headphone.status = HeadphoneStatus.IN_USE
        headphone.current_borrower = data['borrower']
        headphone.last_borrow_time = timezone.now()
        headphone.save()

        result = BorrowRecordSerializer(borrow_record).data
        return Response(result, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def _return(self, request):
        serializer = ReturnActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            headphone = Headphone.objects.select_for_update().get(pk=data['headphone_id'])
        except Headphone.DoesNotExist:
            return Response({'error': '耳机不存在'}, status=status.HTTP_404_NOT_FOUND)

        if not headphone.can_return():
            return Response(
                {'error': f'耳机当前状态为 {headphone.get_status_display()}，无法归还'},
                status=status.HTTP_400_BAD_REQUEST
            )

        borrow_record = BorrowRecord.objects.select_for_update().filter(
            headphone=headphone,
            return_time__isnull=True
        ).order_by('-borrow_time').first()

        if not borrow_record:
            return Response({'error': '未找到对应的领用记录'}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        borrow_record.return_time = now
        borrow_record.battery_after = data['battery_after']
        borrow_record.earpad_damaged_after = data['earpad_damaged_after']
        borrow_record.return_remark = data.get('return_remark', '')
        borrow_record.operator_return = request.user

        if borrow_record.expected_return_time and now > borrow_record.expected_return_time:
            borrow_record.is_overdue = True
            self._create_overdue_abnormal(headphone, borrow_record)

        borrow_record.save()

        headphone.status = HeadphoneStatus.PENDING_DISINFECT
        headphone.battery_level = data['battery_after']
        headphone.earpad_damaged = data['earpad_damaged_after']
        headphone.last_return_time = now
        headphone.current_borrower = ''
        headphone.save()

        self._check_consecutive_low_battery(headphone, data['battery_after'])
        self._check_terminal_conflict(headphone, borrow_record)

        result = BorrowRecordSerializer(borrow_record).data
        return Response(result, status=status.HTTP_200_OK)

    @transaction.atomic
    def _disinfect(self, request):
        serializer = DisinfectActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            headphone = Headphone.objects.select_for_update().get(pk=data['headphone_id'])
        except Headphone.DoesNotExist:
            return Response({'error': '耳机不存在'}, status=status.HTTP_404_NOT_FOUND)

        if not headphone.can_disinfect():
            return Response(
                {'error': f'耳机当前状态为 {headphone.get_status_display()}，无法消杀'},
                status=status.HTTP_400_BAD_REQUEST
            )

        disinfect_record = DisinfectionRecord.objects.create(
            headphone=headphone,
            operator=request.user,
            disinfect_method=data.get('disinfect_method', '酒精擦拭'),
            result=data.get('result', True),
            remark=data.get('remark', '')
        )

        if data.get('result', True):
            if headphone.box:
                pending_count = Headphone.objects.filter(
                    box=headphone.box,
                    status=HeadphoneStatus.PENDING_REVIEW
                ).exclude(pk=headphone.pk).count()
                if pending_count >= headphone.box.capacity:
                    return Response(
                        {'error': f'盒位 {headphone.box.box_no} 已被待复核耳机占满，无法进入待复核状态'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            headphone.status = HeadphoneStatus.PENDING_REVIEW
        else:
            headphone.status = HeadphoneStatus.PENDING_DISINFECT

        headphone.save()

        result = DisinfectionRecordSerializer(disinfect_record).data
        return Response(result, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def _review(self, request):
        serializer = ReviewActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            headphone = Headphone.objects.select_for_update().get(pk=data['headphone_id'])
        except Headphone.DoesNotExist:
            return Response({'error': '耳机不存在'}, status=status.HTTP_404_NOT_FOUND)

        if not headphone.can_review():
            return Response(
                {'error': f'耳机当前状态为 {headphone.get_status_display()}，无法复核'},
                status=status.HTTP_400_BAD_REQUEST
            )

        passed = data.get('passed', True)
        earpad_damaged = data.get('earpad_damaged', False)
        battery_ok = data.get('battery_ok', True)
        appearance_ok = data.get('appearance_ok', True)
        function_ok = data.get('function_ok', True)

        if passed and not (battery_ok and appearance_ok and function_ok):
            passed = False

        review_record = ReviewRecord.objects.create(
            headphone=headphone,
            reviewer=request.user,
            passed=passed,
            earpad_damaged=earpad_damaged,
            battery_ok=battery_ok,
            appearance_ok=appearance_ok,
            function_ok=function_ok,
            remark=data.get('remark', '')
        )

        if passed:
            headphone.status = HeadphoneStatus.AVAILABLE
            if earpad_damaged:
                headphone.earpad_damaged = True
        else:
            headphone.status = HeadphoneStatus.OUT_OF_SERVICE
            reasons = []
            if not battery_ok:
                reasons.append('电量异常')
            if not appearance_ok or earpad_damaged:
                reasons.append('外观异常')
            if not function_ok:
                reasons.append('功能异常')
            if not reasons:
                reasons.append('复核不通过')
            headphone.suspend_reason = data.get('remark', '、'.join(reasons))

        headphone.save()

        result = ReviewRecordSerializer(review_record).data
        return Response(result, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def _suspend(self, request):
        serializer = SuspendActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            headphone = Headphone.objects.select_for_update().get(pk=data['headphone_id'])
        except Headphone.DoesNotExist:
            return Response({'error': '耳机不存在'}, status=status.HTTP_404_NOT_FOUND)

        if headphone.status == HeadphoneStatus.IN_USE:
            return Response(
                {'error': '耳机正在使用中，请先归还再停用'},
                status=status.HTTP_400_BAD_REQUEST
            )

        headphone.status = HeadphoneStatus.OUT_OF_SERVICE
        headphone.suspend_reason = data['reason']
        headphone.save()

        result = HeadphoneSerializer(headphone).data
        return Response(result, status=status.HTTP_200_OK)

    @transaction.atomic
    def _activate(self, request):
        headphone_id = request.data.get('headphone_id')
        if not headphone_id:
            return Response({'error': '缺少 headphone_id 参数'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            headphone = Headphone.objects.select_for_update().get(pk=headphone_id)
        except Headphone.DoesNotExist:
            return Response({'error': '耳机不存在'}, status=status.HTTP_404_NOT_FOUND)

        if headphone.status != HeadphoneStatus.OUT_OF_SERVICE:
            return Response(
                {'error': f'只有停用观察的耳机才能激活，当前状态为 {headphone.get_status_display()}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if headphone.box:
            pending_count = Headphone.objects.filter(
                box=headphone.box,
                status=HeadphoneStatus.PENDING_REVIEW
            ).exclude(pk=headphone.pk).count()
            if pending_count >= headphone.box.capacity:
                return Response(
                    {'error': f'盒位 {headphone.box.box_no} 已被待复核耳机占满，无法进入待复核状态'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        headphone.status = HeadphoneStatus.PENDING_REVIEW
        headphone.suspend_reason = ''
        headphone.save()

        result = HeadphoneSerializer(headphone).data
        return Response(result, status=status.HTTP_200_OK)

    def _check_consecutive_low_battery(self, headphone, current_battery):
        recent_records = BorrowRecord.objects.filter(
            headphone=headphone,
            return_time__isnull=False
        ).order_by('-return_time')[:self.CONSECUTIVE_LOW_BATTERY_COUNT]

        if recent_records.count() < self.CONSECUTIVE_LOW_BATTERY_COUNT:
            return

        all_low = all(
            record.battery_after is not None and record.battery_after < self.LOW_BATTERY_THRESHOLD
            for record in recent_records
        )

        if all_low and current_battery < self.LOW_BATTERY_THRESHOLD:
            batteries = [r.battery_after for r in recent_records]
            AbnormalRecord.objects.get_or_create(
                headphone=headphone,
                abnormal_type='low_battery',
                status=AbnormalStatus.PENDING,
                defaults={
                    'severity': 'medium',
                    'description': (
                        f'耳机 {headphone.serial_no} 连续 {self.CONSECUTIVE_LOW_BATTERY_COUNT} 次'
                        f'归还时电量低于{self.LOW_BATTERY_THRESHOLD}%，'
                        f'最近电量: {batteries}'
                    )
                }
            )

    def _create_overdue_abnormal(self, headphone, borrow_record):
        existing = AbnormalRecord.objects.filter(
            headphone=headphone,
            abnormal_type='overdue',
            status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING]
        ).exists()
        if not existing:
            AbnormalRecord.objects.create(
                headphone=headphone,
                abnormal_type='overdue',
                severity='medium',
                description=(
                    f'耳机 {headphone.serial_no} 归还超时，'
                    f'预计归还时间 {borrow_record.expected_return_time}'
                )
            )

    def _check_terminal_conflict(self, headphone, borrow_record):
        terminal_used = borrow_record.terminal_used
        if not terminal_used or not headphone.compatible_terminal:
            return

        compatible_list = [t.strip() for t in headphone.compatible_terminal.split(',')]
        if terminal_used not in compatible_list:
            existing = AbnormalRecord.objects.filter(
                headphone=headphone,
                abnormal_type='terminal_conflict',
                status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING]
            ).exists()
            if not existing:
                AbnormalRecord.objects.create(
                    headphone=headphone,
                    abnormal_type='terminal_conflict',
                    severity='low',
                    description=(
                        f'耳机 {headphone.serial_no} 适配终端为 {headphone.compatible_terminal}，'
                        f'实际使用终端为 {terminal_used}'
                    )
                )


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    username = serializer.validated_data['username']
    password = serializer.validated_data['password']

    user = authenticate(username=username, password=password)
    if not user:
        return Response({'error': '用户名或密码错误'}, status=status.HTTP_401_UNAUTHORIZED)

    refresh = RefreshToken.for_user(user)
    user_data = UserSerializer(user).data

    return Response({
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': user_data
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def current_user_view(request):
    serializer = UserSerializer(request.user)
    return Response(serializer.data)


def _safe_int(value, default=None, min_value=None, max_value=None):
    if value is None:
        return default
    try:
        result = int(value)
    except (ValueError, TypeError):
        return default
    if min_value is not None and result < min_value:
        return default
    if max_value is not None and result > max_value:
        return default
    return result


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def statistics_view(request):
    result = {}

    batch_no = request.GET.get('batch')
    box_no = request.GET.get('box')
    responsible_person = request.GET.get('responsible_person')
    status = request.GET.get('status')
    battery_min = _safe_int(request.GET.get('battery_min'), min_value=0, max_value=100)
    battery_max = _safe_int(request.GET.get('battery_max'), min_value=0, max_value=100)
    date_start = request.GET.get('date_start')
    date_end = request.GET.get('date_end')
    low_battery_threshold = _safe_int(
        request.GET.get('low_battery_threshold'),
        default=30,
        min_value=1,
        max_value=99
    )

    hp_qs = Headphone.objects.all()
    if batch_no:
        hp_qs = hp_qs.filter(batch__batch_no__icontains=batch_no)
    if box_no:
        hp_qs = hp_qs.filter(box__box_no__icontains=box_no)
    if responsible_person:
        hp_qs = hp_qs.filter(responsible_person__icontains=responsible_person)
    if status:
        valid_statuses = [s for s, _ in HeadphoneStatus.choices]
        if status in valid_statuses:
            hp_qs = hp_qs.filter(status=status)
    if battery_min is not None:
        hp_qs = hp_qs.filter(battery_level__gte=battery_min)
    if battery_max is not None:
        hp_qs = hp_qs.filter(battery_level__lte=battery_max)
    if date_start:
        try:
            hp_qs = hp_qs.filter(created_at__date__gte=date_start)
        except ValueError:
            pass
    if date_end:
        try:
            hp_qs = hp_qs.filter(created_at__date__lte=date_end)
        except ValueError:
            pass

    result['applied_filters'] = {
        'batch': batch_no,
        'box': box_no,
        'responsible_person': responsible_person,
        'status': status,
        'battery_min': battery_min,
        'battery_max': battery_max,
        'date_start': date_start,
        'date_end': date_end,
        'low_battery_threshold': low_battery_threshold,
    }

    total_headphones = hp_qs.count()
    result['total_headphones'] = total_headphones

    status_stats = hp_qs.values('status').annotate(count=Count('id'))
    result['status_stats'] = {item['status']: item['count'] for item in status_stats}

    low_battery_headphones = hp_qs.filter(
        battery_level__lt=low_battery_threshold,
        status__in=[HeadphoneStatus.PENDING_BORROW, HeadphoneStatus.AVAILABLE, HeadphoneStatus.PENDING_REVIEW]
    )
    result['low_battery'] = {
        'count': low_battery_headphones.count(),
        'threshold': low_battery_threshold,
        'headphones': HeadphoneListSerializer(low_battery_headphones, many=True).data
    }

    pending_review_headphones = hp_qs.filter(
        status=HeadphoneStatus.PENDING_REVIEW
    ).select_related('batch', 'box')
    result['pending_review'] = {
        'count': pending_review_headphones.count(),
        'headphones': HeadphoneListSerializer(pending_review_headphones, many=True).data
    }

    pending_disinfect_headphones = hp_qs.filter(
        status=HeadphoneStatus.PENDING_DISINFECT
    )
    result['pending_disinfect'] = {
        'count': pending_disinfect_headphones.count()
    }

    in_use_count = hp_qs.filter(status=HeadphoneStatus.IN_USE).count()
    result['in_use'] = {
        'count': in_use_count
    }

    abnormal_qs = AbnormalRecord.objects.all()
    if batch_no:
        abnormal_qs = abnormal_qs.filter(
            Q(headphone__batch__batch_no__icontains=batch_no) | Q(batch__batch_no__icontains=batch_no)
        )

    pending_abnormal = abnormal_qs.filter(status=AbnormalStatus.PENDING).count()
    processing_abnormal = abnormal_qs.filter(status=AbnormalStatus.PROCESSING).count()
    resolved_abnormal = abnormal_qs.filter(status=AbnormalStatus.RESOLVED).count()
    total_abnormal = abnormal_qs.count()

    result['abnormal_stats'] = {
        'total': total_abnormal,
        'pending': pending_abnormal,
        'processing': processing_abnormal,
        'resolved': resolved_abnormal,
    }

    type_distribution = abnormal_qs.values('abnormal_type').annotate(count=Count('id'))
    result['abnormal_type_distribution'] = [
        {
            'type': item['abnormal_type'],
            'type_display': dict(AbnormalRecord.ABNORMAL_TYPES).get(item['abnormal_type'], item['abnormal_type']),
            'count': item['count']
        }
        for item in type_distribution
    ]

    terminal_conflicts = abnormal_qs.filter(
        abnormal_type='terminal_conflict',
        status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING]
    ).count()
    result['terminal_conflict_count'] = terminal_conflicts

    unresolved_abnormal = pending_abnormal + processing_abnormal
    result['unresolved_abnormal'] = unresolved_abnormal

    batch_stats = hp_qs.values(
        'batch__batch_no', 'batch__name'
    ).annotate(
        total=Count('id'),
        damaged=Count('id', filter=Q(earpad_damaged=True))
    )
    result['batch_stats'] = list(batch_stats)

    return Response(result)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def abnormal_detection_view(request):
    auto_save = request.GET.get('save', 'false').lower() == 'true'
    result = {'detected': [], 'saved_to_records': auto_save}
    consecutive_count = _safe_int(
        request.GET.get('consecutive_count'),
        default=3,
        min_value=2,
        max_value=10
    )
    low_battery_threshold = _safe_int(
        request.GET.get('low_battery_threshold'),
        default=30,
        min_value=1,
        max_value=99
    )

    now = timezone.now()

    low_battery_list = _detect_consecutive_low_battery(consecutive_count, low_battery_threshold)
    if auto_save:
        _save_low_battery_abnormal(low_battery_list, consecutive_count, low_battery_threshold)

    result['detected'].append({
        'type': 'low_battery',
        'name': '连续低电量',
        'count': len(low_battery_list),
        'items': low_battery_list
    })

    batch_damage_list = _detect_batch_earpad_damage()
    if auto_save:
        _save_batch_damage_abnormal(batch_damage_list)

    result['detected'].append({
        'type': 'earpad_damage',
        'name': '同批次耳罩破损偏多',
        'count': len(batch_damage_list),
        'items': batch_damage_list
    })

    overdue_list = _detect_overdue(now)
    if auto_save:
        _save_overdue_abnormal(overdue_list)

    result['detected'].append({
        'type': 'overdue',
        'name': '归还超时',
        'count': len(overdue_list),
        'items': overdue_list
    })

    review_missed_list = _detect_review_missed(now)
    if auto_save:
        _save_review_missed_abnormal(review_missed_list)

    result['detected'].append({
        'type': 'review_missed',
        'name': '复核遗漏',
        'count': len(review_missed_list),
        'items': review_missed_list
    })

    return Response(result)


def _detect_consecutive_low_battery(consecutive_count, threshold):
    low_battery_list = []
    for headphone in Headphone.objects.all():
        recent_records = BorrowRecord.objects.filter(
            headphone=headphone,
            return_time__isnull=False
        ).order_by('-return_time')[:consecutive_count]

        if recent_records.count() < consecutive_count:
            continue

        all_low = all(
            record.battery_after is not None and record.battery_after < threshold
            for record in recent_records
        )

        if all_low:
            batteries = [r.battery_after for r in recent_records]
            low_battery_list.append({
                'headphone_id': headphone.id,
                'serial_no': headphone.serial_no,
                'count': consecutive_count,
                'recent_batteries': batteries
            })
    return low_battery_list


def _save_low_battery_abnormal(items, consecutive_count, threshold):
    for item in items:
        headphone = Headphone.objects.get(pk=item['headphone_id'])
        existing = AbnormalRecord.objects.filter(
            headphone=headphone,
            abnormal_type='low_battery',
            status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING]
        ).exists()
        if not existing:
            AbnormalRecord.objects.create(
                headphone=headphone,
                abnormal_type='low_battery',
                severity='medium',
                description=(
                    f'耳机 {headphone.serial_no} 连续 {consecutive_count} 次'
                    f'归还时电量低于{threshold}%，'
                    f'最近电量: {item["recent_batteries"]}'
                )
            )


def _detect_batch_earpad_damage():
    batch_damage_list = []
    for batch in Batch.objects.all():
        total = batch.headphones.count()
        damaged = batch.headphones.filter(earpad_damaged=True).count()
        if total > 0 and damaged / total > 0.3:
            rate = round(damaged / total * 100, 2)
            batch_damage_list.append({
                'batch_id': batch.id,
                'batch_no': batch.batch_no,
                'batch_name': batch.name,
                'total': total,
                'damaged': damaged,
                'rate': rate
            })
    return batch_damage_list


def _save_batch_damage_abnormal(items):
    for item in items:
        batch = Batch.objects.get(pk=item['batch_id'])
        existing = AbnormalRecord.objects.filter(
            batch=batch,
            abnormal_type='earpad_damage',
            status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING]
        ).exists()
        if not existing:
            AbnormalRecord.objects.create(
                batch=batch,
                abnormal_type='earpad_damage',
                severity='high',
                description=(
                    f'批次 {batch.batch_no} 耳罩破损比例过高: '
                    f'{item["damaged"]}/{item["total"]} ({item["rate"]}%)'
                )
            )


def _detect_overdue(now):
    overdue_list = []
    active_borrows = BorrowRecord.objects.filter(
        return_time__isnull=True,
        expected_return_time__isnull=False
    ).select_related('headphone')
    for record in active_borrows:
        if record.expected_return_time and now > record.expected_return_time:
            overdue_hours = round((now - record.expected_return_time).total_seconds() / 3600, 1)
            overdue_list.append({
                'record_id': record.id,
                'headphone_id': record.headphone.id,
                'serial_no': record.headphone.serial_no,
                'borrower': record.borrower,
                'borrow_time': record.borrow_time,
                'expected_return_time': record.expected_return_time,
                'overdue_hours': overdue_hours
            })
    return overdue_list


def _save_overdue_abnormal(items):
    for item in items:
        headphone = Headphone.objects.get(pk=item['headphone_id'])
        existing = AbnormalRecord.objects.filter(
            headphone=headphone,
            abnormal_type='overdue',
            status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING]
        ).exists()
        if not existing:
            AbnormalRecord.objects.create(
                headphone=headphone,
                abnormal_type='overdue',
                severity='medium',
                description=(
                    f'耳机 {headphone.serial_no} 被 {item["borrower"]} 领用后'
                    f'超时 {item["overdue_hours"]} 小时未归还'
                )
            )


def _detect_review_missed(now):
    review_missed_list = []
    pending_review_headphones = Headphone.objects.filter(
        status=HeadphoneStatus.PENDING_REVIEW
    )
    for hp in pending_review_headphones:
        last_disinfect = DisinfectionRecord.objects.filter(
            headphone=hp
        ).order_by('-disinfect_time').first()
        if last_disinfect and (now - last_disinfect.disinfect_time) > timedelta(hours=24):
            pending_hours = round((now - last_disinfect.disinfect_time).total_seconds() / 3600, 1)
            review_missed_list.append({
                'headphone_id': hp.id,
                'serial_no': hp.serial_no,
                'disinfect_time': last_disinfect.disinfect_time,
                'pending_hours': pending_hours
            })
    return review_missed_list


def _save_review_missed_abnormal(items):
    for item in items:
        headphone = Headphone.objects.get(pk=item['headphone_id'])
        existing = AbnormalRecord.objects.filter(
            headphone=headphone,
            abnormal_type='review_missed',
            status__in=[AbnormalStatus.PENDING, AbnormalStatus.PROCESSING]
        ).exists()
        if not existing:
            AbnormalRecord.objects.create(
                headphone=headphone,
                abnormal_type='review_missed',
                severity='low',
                description=(
                    f'耳机 {headphone.serial_no} 消杀完成后'
                    f'超过 {item["pending_hours"]} 小时未复核'
                )
            )
