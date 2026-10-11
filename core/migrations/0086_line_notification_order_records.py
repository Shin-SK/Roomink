from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0085_store_business_day_boundary_and_shift_start_offset"),
    ]

    operations = [
        migrations.AddField(
            model_name="linenotificationlog",
            name="message",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="linenotificationlog",
            name="order",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="line_notification_logs",
                to="core.order",
            ),
        ),
        migrations.AlterField(
            model_name="linenotificationlog",
            name="shift_assignment",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="line_notification_logs",
                to="core.shiftassignment",
            ),
        ),
    ]
