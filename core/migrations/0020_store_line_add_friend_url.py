from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0019_line_notification_log"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="line_add_friend_url",
            field=models.URLField(blank=True, default=""),
        ),
    ]
