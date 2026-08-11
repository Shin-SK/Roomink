import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0049_shiftendalert"),
    ]

    operations = [
        migrations.CreateModel(
            name="PublicBookingVerification",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("phone", models.CharField(max_length=20)),
                ("display_name", models.CharField(max_length=50)),
                ("booking_payload", models.JSONField()),
                ("code_hash", models.CharField(max_length=255)),
                ("failed_attempts", models.PositiveSmallIntegerField(default=0)),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "sms_log",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="public_booking_verifications",
                        to="core.smslog",
                    ),
                ),
                (
                    "store",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="public_booking_verifications",
                        to="core.store",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["phone", "-created_at"],
                        name="core_publi_phone_eb42af_idx",
                    ),
                    models.Index(
                        fields=["expires_at"],
                        name="core_publi_expires_c8e502_idx",
                    ),
                ],
            },
        ),
    ]
