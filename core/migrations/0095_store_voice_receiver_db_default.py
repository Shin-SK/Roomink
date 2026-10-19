from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0094_merge_work_line")]

    operations = [
        migrations.AlterField(
            model_name="store",
            name="voice_receiver",
            field=models.CharField(
                choices=[("groundwire", "Groundwire"), ("work", "Roomink Work")],
                default="groundwire",
                db_default="groundwire",
                max_length=12,
            ),
        ),
    ]
