from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta

from headphones.models import (
    Batch, Box, Headphone, BorrowRecord, DisinfectionRecord,
    ReviewRecord, AbnormalRecord, UserProfile, UserRole, HeadphoneStatus
)


class Command(BaseCommand):
    help = '初始化系统数据，包括用户、批次、盒位、耳机和示例流转数据'

    def handle(self, *args, **options):
        self.stdout.write('开始初始化数据...')

        self._create_users()
        self._create_batches()
        self._create_boxes()
        self._create_headphones()
        self._create_sample_records()

        self.stdout.write(self.style.SUCCESS('数据初始化完成！'))
        self.stdout.write('管理员账号: admin / admin123456')
        self.stdout.write('现场人员账号: staff / staff123456')

    def _create_users(self):
        self.stdout.write('  - 创建用户账号...')

        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@example.com',
                'first_name': '系统',
                'last_name': '管理员',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created:
            admin_user.set_password('admin123456')
            admin_user.save()

        admin_profile, _ = UserProfile.objects.get_or_create(user=admin_user)
        admin_profile.role = UserRole.ADMIN
        admin_profile.phone = '13800138001'
        admin_profile.department = '运维管理部'
        admin_profile.save()

        staff_user, created = User.objects.get_or_create(
            username='staff',
            defaults={
                'email': 'staff@example.com',
                'first_name': '现场',
                'last_name': '工作人员',
                'is_staff': False,
                'is_superuser': False,
            }
        )
        if created:
            staff_user.set_password('staff123456')
            staff_user.save()

        staff_profile, _ = UserProfile.objects.get_or_create(user=staff_user)
        staff_profile.role = UserRole.FIELD_STAFF
        staff_profile.phone = '13800138002'
        staff_profile.department = '现场服务部'
        staff_profile.save()

        self.admin_user = admin_user
        self.staff_user = staff_user

    def _create_batches(self):
        self.stdout.write('  - 创建批次数据...')

        batch_data = [
            {'batch_no': 'B2024001', 'name': '2024年春季采购批次', 'total_quantity': 10},
            {'batch_no': 'B2024002', 'name': '2024年夏季采购批次', 'total_quantity': 8},
            {'batch_no': 'B2024003', 'name': '2024年秋季采购批次', 'total_quantity': 12},
        ]

        self.batches = []
        for data in batch_data:
            batch, _ = Batch.objects.get_or_create(
                batch_no=data['batch_no'],
                defaults=data
            )
            self.batches.append(batch)

    def _create_boxes(self):
        self.stdout.write('  - 创建盒位数据...')

        box_data = [
            {'box_no': 'BOX-A01', 'location': 'A区第1排', 'capacity': 1},
            {'box_no': 'BOX-A02', 'location': 'A区第1排', 'capacity': 1},
            {'box_no': 'BOX-A03', 'location': 'A区第2排', 'capacity': 1},
            {'box_no': 'BOX-A04', 'location': 'A区第2排', 'capacity': 1},
            {'box_no': 'BOX-B01', 'location': 'B区第1排', 'capacity': 1},
            {'box_no': 'BOX-B02', 'location': 'B区第1排', 'capacity': 1},
            {'box_no': 'BOX-B03', 'location': 'B区第2排', 'capacity': 1},
            {'box_no': 'BOX-B04', 'location': 'B区第2排', 'capacity': 1},
            {'box_no': 'BOX-C01', 'location': 'C区第1排', 'capacity': 1},
            {'box_no': 'BOX-C02', 'location': 'C区第1排', 'capacity': 1},
        ]

        self.boxes = []
        for data in box_data:
            box, _ = Box.objects.get_or_create(
                box_no=data['box_no'],
                defaults=data
            )
            self.boxes.append(box)

    def _create_headphones(self):
        self.stdout.write('  - 创建耳机数据...')

        headphone_data = []

        for i in range(10):
            headphone_data.append({
                'serial_no': f'HP-B01-{i+1:02d}',
                'batch_idx': 0,
                'box_idx': i if i < 10 else None,
                'compatible_terminal': 'iPhone 15, iPad Pro',
                'responsible_person': '张三',
                'battery_level': 100,
                'status': HeadphoneStatus.PENDING_BORROW,
                'earpad_damaged': False,
            })

        for i in range(8):
            headphone_data.append({
                'serial_no': f'HP-B02-{i+1:02d}',
                'batch_idx': 1,
                'box_idx': None,
                'compatible_terminal': 'Samsung S24, Google Pixel',
                'responsible_person': '李四',
                'battery_level': 85,
                'status': HeadphoneStatus.PENDING_BORROW,
                'earpad_damaged': False,
            })

        for i in range(12):
            damage_flag = i in [2, 5, 9]
            headphone_data.append({
                'serial_no': f'HP-B03-{i+1:02d}',
                'batch_idx': 2,
                'box_idx': None,
                'compatible_terminal': '华为Mate60, 小米14',
                'responsible_person': '王五',
                'battery_level': 75 if i % 3 == 0 else 95,
                'status': HeadphoneStatus.PENDING_BORROW,
                'earpad_damaged': damage_flag,
            })

        self.headphones = []
        for data in headphone_data:
            batch = self.batches[data.pop('batch_idx')]
            box_idx = data.pop('box_idx')
            box = self.boxes[box_idx] if box_idx is not None and box_idx < len(self.boxes) else None

            hp, created = Headphone.objects.get_or_create(
                serial_no=data['serial_no'],
                defaults={
                    **data,
                    'batch': batch,
                    'box': box,
                }
            )
            self.headphones.append(hp)

    def _create_sample_records(self):
        self.stdout.write('  - 创建示例流转记录...')

        now = timezone.now()

        hp1 = self.headphones[0]
        borrow_record1 = BorrowRecord.objects.create(
            headphone=hp1,
            borrower='测试用户A',
            borrow_time=now - timedelta(days=2, hours=3),
            expected_return_time=now - timedelta(days=2) + timedelta(hours=8),
            return_time=now - timedelta(days=2, hours=1),
            battery_before=100,
            battery_after=75,
            earpad_damaged_before=False,
            earpad_damaged_after=False,
            terminal_used='iPhone 15',
            operator_borrow=self.staff_user,
            operator_return=self.staff_user,
            is_overdue=False,
        )

        DisinfectionRecord.objects.create(
            headphone=hp1,
            operator=self.staff_user,
            disinfect_time=now - timedelta(days=2),
            disinfect_method='酒精擦拭',
            result=True,
        )

        ReviewRecord.objects.create(
            headphone=hp1,
            reviewer=self.admin_user,
            review_time=now - timedelta(days=1, hours=20),
            passed=True,
            earpad_damaged=False,
            battery_ok=True,
            appearance_ok=True,
            function_ok=True,
        )

        hp1.status = HeadphoneStatus.AVAILABLE
        hp1.save()

        hp2 = self.headphones[1]
        BorrowRecord.objects.create(
            headphone=hp2,
            borrower='测试用户B',
            borrow_time=now - timedelta(hours=5),
            expected_return_time=now + timedelta(hours=3),
            battery_before=100,
            earpad_damaged_before=False,
            terminal_used='iPad Pro',
            operator_borrow=self.staff_user,
        )
        hp2.status = HeadphoneStatus.IN_USE
        hp2.current_borrower = '测试用户B'
        hp2.last_borrow_time = now - timedelta(hours=5)
        hp2.save()

        hp3 = self.headphones[2]
        BorrowRecord.objects.create(
            headphone=hp3,
            borrower='测试用户C',
            borrow_time=now - timedelta(hours=8),
            expected_return_time=now - timedelta(hours=2),
            battery_before=90,
            earpad_damaged_before=False,
            terminal_used='iPhone 15',
            operator_borrow=self.staff_user,
        )
        hp3.status = HeadphoneStatus.IN_USE
        hp3.current_borrower = '测试用户C'
        hp3.last_borrow_time = now - timedelta(hours=8)
        hp3.save()

        hp4 = self.headphones[3]
        borrow4 = BorrowRecord.objects.create(
            headphone=hp4,
            borrower='测试用户D',
            borrow_time=now - timedelta(hours=10),
            expected_return_time=now - timedelta(hours=4),
            return_time=now - timedelta(hours=2),
            battery_before=95,
            battery_after=25,
            earpad_damaged_before=False,
            earpad_damaged_after=False,
            terminal_used='Samsung S24',
            operator_borrow=self.staff_user,
            operator_return=self.staff_user,
            is_overdue=True,
        )
        hp4.status = HeadphoneStatus.PENDING_DISINFECT
        hp4.battery_level = 25
        hp4.last_return_time = now - timedelta(hours=2)
        hp4.current_borrower = ''
        hp4.save()

        AbnormalRecord.objects.create(
            headphone=hp4,
            abnormal_type='overdue',
            severity='medium',
            description=f'耳机 {hp4.serial_no} 归还超时',
            resolved=False,
        )

        hp5 = self.headphones[4]
        BorrowRecord.objects.create(
            headphone=hp5,
            borrower='测试用户E',
            borrow_time=now - timedelta(days=1, hours=10),
            expected_return_time=now - timedelta(days=1, hours=2),
            return_time=now - timedelta(days=1, hours=3),
            battery_before=100,
            battery_after=45,
            earpad_damaged_before=False,
            earpad_damaged_after=False,
            terminal_used='华为Mate60',
            operator_borrow=self.staff_user,
            operator_return=self.staff_user,
            is_overdue=False,
        )
        DisinfectionRecord.objects.create(
            headphone=hp5,
            operator=self.staff_user,
            disinfect_time=now - timedelta(days=1, hours=2),
            disinfect_method='酒精擦拭',
            result=True,
        )
        hp5.status = HeadphoneStatus.PENDING_REVIEW
        hp5.battery_level = 45
        hp5.last_return_time = now - timedelta(days=1, hours=3)
        hp5.save()

        hp6 = self.headphones[5]
        hp6.status = HeadphoneStatus.OUT_OF_SERVICE
        hp6.suspend_reason = '耳罩破损严重，待更换'
        hp6.earpad_damaged = True
        hp6.save()

        AbnormalRecord.objects.create(
            headphone=hp6,
            batch=hp6.batch,
            abnormal_type='earpad_damage',
            severity='high',
            description=f'耳机 {hp6.serial_no} 耳罩破损严重，需要更换',
            resolved=False,
        )

        for i in range(3):
            hp = self.headphones[10 + i]
            BorrowRecord.objects.create(
                headphone=hp,
                borrower=f'低电量测试用户{i+1}',
                borrow_time=now - timedelta(days=i + 1),
                expected_return_time=now - timedelta(days=i) + timedelta(hours=6),
                return_time=now - timedelta(days=i) + timedelta(hours=7),
                battery_before=100,
                battery_after=20 + i * 5,
                earpad_damaged_before=False,
                earpad_damaged_after=False,
                terminal_used='华为Mate60',
                operator_borrow=self.staff_user,
                operator_return=self.staff_user,
                is_overdue=True,
            )

        self.stdout.write('  - 示例数据创建完成')
