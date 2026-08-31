from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0064_sipreceptiondevice_and_link_device"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SupportConversation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user_role", models.CharField(max_length=20)),
                ("page_path", models.CharField(blank=True, default="", max_length=500)),
                ("page_title", models.CharField(blank=True, default="", max_length=200)),
                ("kind", models.CharField(choices=[("SUPPORT", "操作・不具合の問い合わせ"), ("FEATURE", "ご意見・機能要望")], default="SUPPORT", max_length=10)),
                ("status", models.CharField(choices=[("OPEN", "対応中"), ("RESOLVED", "解決済み"), ("ESCALATED", "運営確認待ち")], default="OPEN", max_length=12)),
                ("summary", models.TextField(blank=True, default="")),
                ("unresolved_reason", models.TextField(blank=True, default="")),
                ("unresolved_at", models.DateTimeField(blank=True, null=True)),
                ("inquiry_submitted_at", models.DateTimeField(blank=True, null=True)),
                ("ai_reply_draft", models.TextField(blank=True, default="")),
                ("auto_reply_scheduled_at", models.DateTimeField(blank=True, null=True)),
                ("auto_reply_sent_at", models.DateTimeField(blank=True, null=True)),
                ("auto_reply_cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("user_last_viewed_at", models.DateTimeField(blank=True, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("escalated_at", models.DateTimeField(blank=True, null=True)),
                ("slack_notified_at", models.DateTimeField(blank=True, null=True)),
                ("trend_notified_at", models.DateTimeField(blank=True, null=True)),
                ("slack_error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="support_conversations", to="core.store")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="support_conversations", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-updated_at", "-id"]},
        ),
        migrations.AddIndex(
            model_name="supportconversation",
            index=models.Index(fields=["store", "status"], name="core_sup_store_status_idx"),
        ),
        migrations.AddIndex(
            model_name="supportconversation",
            index=models.Index(fields=["user", "created_at"], name="core_sup_user_created_idx"),
        ),
        migrations.CreateModel(
            name="SupportMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("USER", "利用者"), ("ASSISTANT", "サポート"), ("OPERATOR", "運営")], max_length=10)),
                ("content", models.TextField()),
                ("sources", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="core.supportconversation")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
    ]
