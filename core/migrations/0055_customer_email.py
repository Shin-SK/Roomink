from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0054_room_map_url_room_sms_notice"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="email",
            field=models.EmailField(blank=True, default="", max_length=254),
        ),
        migrations.AddField(
            model_name="customer",
            name="legacy_usage_history",
            field=models.TextField(
                blank=True,
                default="",
                help_text="旧システムから移行した利用履歴（参照用・売上集計対象外）",
            ),
        ),
    ]
