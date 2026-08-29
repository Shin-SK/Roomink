from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0062_castnote_sort_order"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="sip_domain",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Twilio SIP Domain（例: store.sip.twilio.com）",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="store",
            name="sip_password",
            field=models.TextField(
                blank=True,
                default="",
                help_text="受付アプリ用SIPパスワード（API応答には含めない）",
            ),
        ),
        migrations.AddField(
            model_name="store",
            name="sip_username",
            field=models.CharField(
                blank=True,
                default="",
                help_text="受付アプリがTwilio SIPへ登録するときの店舗別ユーザー名",
                max_length=64,
            ),
        ),
        migrations.CreateModel(
            name="SipProvisioningLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_sip_provisioning_links",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "store",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sip_provisioning_links",
                        to="core.store",
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
    ]
