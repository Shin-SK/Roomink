from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0086_line_notification_order_records"),
    ]

    operations = [
        migrations.AlterField(
            model_name="linenotificationlog",
            name="notification_type",
            field=models.CharField(
                choices=[
                    ("MORNING", "朝通知"),
                    ("TWO_HOURS_BEFORE", "2時間前"),
                    ("FIFTEEN_MIN_BEFORE", "15分前"),
                    ("SHIFT_END_70", "終了70分前"),
                    ("ORDER_CONFIRMED", "予約確定"),
                ],
                max_length=20,
            ),
        ),
    ]
