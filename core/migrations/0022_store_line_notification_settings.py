from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0021_store_line_multi_store"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="line_morning_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="store",
            name="line_morning_time",
            field=models.TimeField(default="09:00"),
        ),
        migrations.AddField(
            model_name="store",
            name="line_two_hours_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="store",
            name="line_fifteen_minutes_enabled",
            field=models.BooleanField(default=True),
        ),
    ]
