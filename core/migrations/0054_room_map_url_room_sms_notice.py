from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0053_store_shift_end_line_alert"),
    ]

    operations = [
        migrations.AddField(
            model_name="room",
            name="map_url",
            field=models.URLField(
                blank=True,
                default="",
                help_text="予約確認SMSへ掲載する地図URL",
                max_length=500,
            ),
        ),
        migrations.AddField(
            model_name="room",
            name="sms_notice",
            field=models.TextField(
                blank=True,
                default="",
                help_text="予約確認SMSへ掲載するルーム固有の注意事項",
            ),
        ),
    ]
