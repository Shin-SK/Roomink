from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core", "0103_shift_attendance")]
    operations = [migrations.CreateModel(
        name="VoiceDiagnosticEvent",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("event_key", models.CharField(max_length=64, unique=True)),
            ("stage", models.CharField(max_length=32)),
            ("call_sid", models.CharField(max_length=128)),
            ("details", models.JSONField(default=dict)),
            ("received_at", models.DateTimeField(auto_now_add=True)),
            ("call", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="diagnostic_events", to="core.calllog")),
        ],
    )]
