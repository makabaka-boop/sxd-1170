from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_resolved_to_status(apps, schema_editor):
    AbnormalRecord = apps.get_model('headphones', 'AbnormalRecord')
    AbnormalRecord.objects.filter(resolved=True).update(status='resolved')
    AbnormalRecord.objects.filter(resolved=False).update(status='pending')


def reverse_migrate_status_to_resolved(apps, schema_editor):
    AbnormalRecord = apps.get_model('headphones', 'AbnormalRecord')
    AbnormalRecord.objects.filter(status='resolved').update(resolved=True)
    AbnormalRecord.objects.exclude(status='resolved').update(resolved=False)


class Migration(migrations.Migration):

    dependencies = [
        ('headphones', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='abnormalrecord',
            name='status',
            field=models.CharField(
                choices=[('pending', '未处理'), ('processing', '处理中'), ('resolved', '已处理')],
                default='pending',
                max_length=20,
                verbose_name='处理状态'
            ),
        ),
        migrations.AddField(
            model_name='abnormalrecord',
            name='handler',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='handled_abnormal_records',
                to=settings.AUTH_USER_MODEL,
                verbose_name='处理人'
            ),
        ),
        migrations.AddField(
            model_name='abnormalrecord',
            name='handle_time',
            field=models.DateTimeField(blank=True, null=True, verbose_name='处理时间'),
        ),
        migrations.RunPython(migrate_resolved_to_status, reverse_migrate_status_to_resolved),
        migrations.RemoveField(
            model_name='abnormalrecord',
            name='resolved',
        ),
    ]
