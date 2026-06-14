import django_filters
from .models import Headphone, BorrowRecord, AbnormalRecord, DisinfectionRecord, ReviewRecord


class HeadphoneFilter(django_filters.FilterSet):
    batch = django_filters.CharFilter(field_name='batch__batch_no', lookup_expr='icontains')
    batch_id = django_filters.NumberFilter(field_name='batch_id')
    box = django_filters.CharFilter(field_name='box__box_no', lookup_expr='icontains')
    box_id = django_filters.NumberFilter(field_name='box_id')
    responsible_person = django_filters.CharFilter(lookup_expr='icontains')
    status = django_filters.CharFilter(lookup_expr='exact')
    battery_min = django_filters.NumberFilter(field_name='battery_level', lookup_expr='gte')
    battery_max = django_filters.NumberFilter(field_name='battery_level', lookup_expr='lte')
    serial_no = django_filters.CharFilter(lookup_expr='icontains')
    compatible_terminal = django_filters.CharFilter(lookup_expr='icontains')
    created_start = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    created_end = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')
    earpad_damaged = django_filters.BooleanFilter()

    class Meta:
        model = Headphone
        fields = ['batch', 'box', 'responsible_person', 'status', 'earpad_damaged']


class BorrowRecordFilter(django_filters.FilterSet):
    headphone = django_filters.CharFilter(field_name='headphone__serial_no', lookup_expr='icontains')
    headphone_id = django_filters.NumberFilter(field_name='headphone_id')
    borrower = django_filters.CharFilter(lookup_expr='icontains')
    batch = django_filters.CharFilter(field_name='headphone__batch__batch_no', lookup_expr='icontains')
    borrow_start = django_filters.DateTimeFilter(field_name='borrow_time', lookup_expr='gte')
    borrow_end = django_filters.DateTimeFilter(field_name='borrow_time', lookup_expr='lte')
    return_start = django_filters.DateTimeFilter(field_name='return_time', lookup_expr='gte')
    return_end = django_filters.DateTimeFilter(field_name='return_time', lookup_expr='lte')
    is_overdue = django_filters.BooleanFilter()
    has_returned = django_filters.BooleanFilter(method='filter_has_returned')

    class Meta:
        model = BorrowRecord
        fields = ['headphone', 'borrower', 'is_overdue']

    def filter_has_returned(self, queryset, name, value):
        if value:
            return queryset.filter(return_time__isnull=False)
        return queryset.filter(return_time__isnull=True)


class AbnormalRecordFilter(django_filters.FilterSet):
    abnormal_type = django_filters.CharFilter(lookup_expr='exact')
    severity = django_filters.CharFilter(lookup_expr='exact')
    headphone = django_filters.CharFilter(field_name='headphone__serial_no', lookup_expr='icontains')
    batch = django_filters.CharFilter(field_name='batch__batch_no', lookup_expr='icontains')
    status = django_filters.CharFilter(lookup_expr='exact')
    handler = django_filters.CharFilter(field_name='handler__username', lookup_expr='icontains')
    detected_start = django_filters.DateTimeFilter(field_name='detected_time', lookup_expr='gte')
    detected_end = django_filters.DateTimeFilter(field_name='detected_time', lookup_expr='lte')
    handle_start = django_filters.DateTimeFilter(field_name='handle_time', lookup_expr='gte')
    handle_end = django_filters.DateTimeFilter(field_name='handle_time', lookup_expr='lte')

    class Meta:
        model = AbnormalRecord
        fields = ['abnormal_type', 'severity', 'status']


class DisinfectionRecordFilter(django_filters.FilterSet):
    headphone = django_filters.CharFilter(field_name='headphone__serial_no', lookup_expr='icontains')
    result = django_filters.BooleanFilter()
    operator = django_filters.CharFilter(field_name='operator__username', lookup_expr='icontains')
    disinfect_start = django_filters.DateTimeFilter(field_name='disinfect_time', lookup_expr='gte')
    disinfect_end = django_filters.DateTimeFilter(field_name='disinfect_time', lookup_expr='lte')

    class Meta:
        model = DisinfectionRecord
        fields = ['headphone', 'result']


class ReviewRecordFilter(django_filters.FilterSet):
    headphone = django_filters.CharFilter(field_name='headphone__serial_no', lookup_expr='icontains')
    passed = django_filters.BooleanFilter()
    reviewer = django_filters.CharFilter(field_name='reviewer__username', lookup_expr='icontains')
    review_start = django_filters.DateTimeFilter(field_name='review_time', lookup_expr='gte')
    review_end = django_filters.DateTimeFilter(field_name='review_time', lookup_expr='lte')

    class Meta:
        model = ReviewRecord
        fields = ['headphone', 'passed']
