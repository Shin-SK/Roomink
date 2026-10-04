# Generated manually to keep the migration reviewable alongside the intake design.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0074_store_line_activation"),
    ]

    operations = [
        migrations.CreateModel(
            name="OperationsLineContact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("line_user_id", models.CharField(max_length=64, unique=True)),
                ("display_name", models.CharField(blank=True, default="", max_length=255)),
                ("status", models.CharField(choices=[("PENDING", "承認待ち"), ("ACTIVE", "利用可"), ("DISABLED", "停止")], default="PENDING", max_length=10)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("store", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="operations_line_contacts", to="core.store")),
            ],
        ),
        migrations.CreateModel(
            name="OperationsCase",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("TRIAGE", "追加確認中"), ("READY", "運営判断待ち"), ("IN_PROGRESS", "作業中"), ("STAGING", "ステージング確認待ち"), ("PRODUCTION", "本番承認待ち"), ("COMPLETED", "完了"), ("BLOCKED", "保留")], default="TRIAGE", max_length=12)),
                ("category", models.CharField(choices=[("INCIDENT", "障害・緊急"), ("BUG", "不具合"), ("CHANGE", "修正・要望"), ("QUESTION", "質問"), ("OTHER", "その他")], default="OTHER", max_length=12)),
                ("summary", models.TextField(blank=True, default="")),
                ("missing_information", models.JSONField(blank=True, default=list)),
                ("slack_channel_id", models.CharField(blank=True, default="", max_length=64)),
                ("slack_thread_ts", models.CharField(blank=True, default="", max_length=64)),
                ("slack_permalink", models.URLField(blank=True, default="")),
                ("slack_error", models.TextField(blank=True, default="")),
                ("notion_page_id", models.CharField(blank=True, default="", max_length=64)),
                ("notion_error", models.TextField(blank=True, default="")),
                ("triage_requested_at", models.DateTimeField(blank=True, null=True)),
                ("triaged_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("reporter", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="cases", to="core.operationslinecontact")),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="operations_cases", to="core.store")),
            ],
            options={"ordering": ["-updated_at", "-id"]},
        ),
        migrations.CreateModel(
            name="OperationsCaseMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("REPORTER", "店舗運営"), ("ASSISTANT", "受付AI"), ("OPERATOR", "Roomink運営")], max_length=12)),
                ("content", models.TextField(blank=True, default="")),
                ("line_event_id", models.CharField(blank=True, db_index=True, default=None, max_length=100, null=True, unique=True)),
                ("line_message_id", models.CharField(blank=True, db_index=True, default="", max_length=100)),
                ("withdrawn_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("case", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="core.operationscase")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.AddIndex(
            model_name="operationslinecontact",
            index=models.Index(fields=["store", "status"], name="core_opsl_store_status_idx"),
        ),
        migrations.AddIndex(
            model_name="operationscase",
            index=models.Index(fields=["store", "status"], name="core_opsc_store_status_idx"),
        ),
        migrations.AddIndex(
            model_name="operationscase",
            index=models.Index(fields=["reporter", "updated_at"], name="core_opsc_reporter_updated_idx"),
        ),
    ]
