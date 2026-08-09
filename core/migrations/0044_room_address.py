from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0043_shiftrequest_end_day_offsets"),
    ]

    operations = [
        migrations.AddField(
            model_name="room",
            name="address",
            field=models.CharField(
                blank=True,
                default="",
                help_text="予約確定後に顧客マイページへ表示する住所",
                max_length=255,
            ),
        ),
    ]
