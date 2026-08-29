from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0063_store_sip_settings_sipprovisioninglink"),
    ]

    operations = [
        migrations.CreateModel(
            name="SipReceptionDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=80)),
                ("sip_username", models.CharField(max_length=64, unique=True)),
                (
                    "provisioning_password",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Groundwire初期設定用。使い切り画面表示後に消去する。",
                    ),
                ),
                ("twilio_credential_sid", models.CharField(blank=True, default="", max_length=34)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("provisioned_at", models.DateTimeField(blank=True, null=True)),
                ("disabled_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_sip_reception_devices",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "store",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sip_reception_devices",
                        to="core.store",
                    ),
                ),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.AddField(
            model_name="sipprovisioninglink",
            name="device",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="provisioning_links",
                to="core.sipreceptiondevice",
            ),
        ),
    ]
