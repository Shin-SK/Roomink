import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0048_order_service_recipient_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="ShiftEndAlert",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("alert_at", models.DateTimeField()),
                (
                    "status",
                    models.CharField(
                        choices=[("OPEN", "対応待ち"), ("RESOLVED", "解消済み")],
                        default="OPEN",
                        max_length=10,
                    ),
                ),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "cast",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shift_end_alerts",
                        to="core.cast",
                    ),
                ),
                (
                    "shift_assignment",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shift_end_alert",
                        to="core.shiftassignment",
                    ),
                ),
                (
                    "store",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shift_end_alerts",
                        to="core.store",
                    ),
                ),
            ],
            options={
                "ordering": ["-alert_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["store", "status"],
                        name="core_sea_store_status_idx",
                    ),
                    models.Index(
                        fields=["alert_at"],
                        name="core_sea_alert_at_idx",
                    ),
                ],
            },
        ),
    ]
