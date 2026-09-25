from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0070_store_guest_contact_phone_and_memo"),
    ]

    operations = [
        migrations.AddField(
            model_name="calllog",
            name="duration_seconds",
            field=models.PositiveIntegerField(
                default=0,
                help_text="TwilioのStatusCallbackで確定した通話時間（秒）",
            ),
        ),
        migrations.CreateModel(
            name="CallLogReadReceipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("seen_at", models.DateTimeField(auto_now_add=True)),
                ("call", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="read_receipts", to="core.calllog")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="call_read_receipts", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["seen_at", "id"]},
        ),
        migrations.AddConstraint(
            model_name="calllogreadreceipt",
            constraint=models.UniqueConstraint(fields=("call", "user"), name="unique_call_read_receipt"),
        ),
    ]
