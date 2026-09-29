from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0071_calllog_duration_and_read_receipts"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="timeline_status",
            field=models.CharField(
                choices=[
                    ("AUTO", "自動表示"),
                    ("SMS_SENT", "SMS送信済み"),
                    ("SMS_CONFIRMED", "SMS確認済み"),
                    ("CARD_PAID", "カード決済済み"),
                ],
                default="AUTO",
                help_text="予約タイムライン上の手動表示区分。予約状態そのものには影響しない。",
                max_length=20,
            ),
        ),
    ]
