from django.db import migrations, models

import core.models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0052_order_service_recipient_customer"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="line_operations_link_code",
            field=models.CharField(
                blank=True,
                default=core.models.generate_line_operations_link_code,
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="store",
            name="line_operations_linked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="store",
            name="line_operations_recipient_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="store",
            name="line_operations_recipient_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("user", "個人トーク"),
                    ("group", "グループ"),
                    ("room", "複数人トーク"),
                ],
                default="",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="store",
            name="line_shift_end_alert_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="linenotificationlog",
            name="notification_type",
            field=models.CharField(
                choices=[
                    ("MORNING", "朝通知"),
                    ("TWO_HOURS_BEFORE", "2時間前"),
                    ("FIFTEEN_MIN_BEFORE", "15分前"),
                    ("SHIFT_END_70", "終了70分前"),
                ],
                max_length=20,
            ),
        ),
    ]
