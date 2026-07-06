import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0033_storephonenumber_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="shiftrequest",
            name="approved_date",
            field=models.DateField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="shiftrequest",
            name="approved_start_time",
            field=models.TimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="shiftrequest",
            name="approved_end_time",
            field=models.TimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="shiftrequest",
            name="approved_room",
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="approved_shift_requests",
                to="core.room",
            ),
        ),
        migrations.AddField(
            model_name="shiftrequest",
            name="decided_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="shiftrequest",
            name="decided_by",
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="decided_shift_requests",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
