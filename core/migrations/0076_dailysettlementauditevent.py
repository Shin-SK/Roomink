import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0075_operationslineinboxmessage_operationslineinboxattachment"),
    ]

    operations = [
        migrations.CreateModel(
            name="DailySettlementAuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("LOCK", "確定"), ("UNLOCK", "解除")], max_length=10)),
                ("snapshot_json", models.JSONField(blank=True, default=dict)),
                ("reason", models.CharField(blank=True, default="", max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("acted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="daily_settlement_audit_events", to=settings.AUTH_USER_MODEL)),
                ("settlement", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="audit_events", to="core.dailysettlement")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.AddIndex(
            model_name="dailysettlementauditevent",
            index=models.Index(fields=["settlement", "created_at"], name="core_dailys_settlem_6f313f_idx"),
        ),
    ]
