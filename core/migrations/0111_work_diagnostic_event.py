from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0110_customer_attention_memo")]
    operations = [
        migrations.CreateModel(
            name="WorkDiagnosticEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_id", models.UUIDField()),
                ("call_sid", models.CharField(blank=True, max_length=34)),
                ("stage", models.CharField(max_length=32)),
                ("observed_at", models.DateTimeField()),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("snapshot", models.JSONField(default=dict)),
                ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="core.workdevice")),
            ],
            options={
                "indexes": [models.Index(fields=["call_sid"], name="work_diagnostic_call_idx")],
                "constraints": [models.UniqueConstraint(fields=("device", "event_id"), name="work_diagnostic_device_event")],
            },
        ),
    ]
