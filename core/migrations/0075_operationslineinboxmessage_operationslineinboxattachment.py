# Generated manually for the operations LINE read-only inbox.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0074_store_line_activation")]

    operations = [
        migrations.CreateModel(
            name="OperationsLineInboxMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("line_event_id", models.CharField(db_index=True, max_length=100, unique=True)),
                ("line_message_id", models.CharField(blank=True, db_index=True, default="", max_length=100)),
                ("source_type", models.CharField(blank=True, default="", max_length=12)),
                ("source_id", models.CharField(blank=True, db_index=True, default="", max_length=100)),
                ("sender_user_id", models.CharField(blank=True, default="", max_length=100)),
                ("message_type", models.CharField(choices=[("text", "テキスト"), ("image", "画像"), ("video", "動画"), ("audio", "音声"), ("file", "ファイル"), ("other", "その他")], max_length=12)),
                ("text", models.TextField(blank=True, default="")),
                ("received_at", models.DateTimeField()),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("withdrawn_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-received_at", "-id"]},
        ),
        migrations.CreateModel(
            name="OperationsLineInboxAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("line_message_id", models.CharField(db_index=True, max_length=100)),
                ("filename", models.CharField(blank=True, default="", max_length=255)),
                ("content_type", models.CharField(blank=True, default="", max_length=255)),
                ("size_bytes", models.PositiveBigIntegerField(default=0)),
                ("duration_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("content", models.BinaryField(blank=True, editable=False, null=True)),
                ("status", models.CharField(choices=[("PENDING", "取得待ち"), ("STORED", "保存済み"), ("TOO_LARGE", "容量超過"), ("FAILED", "取得失敗"), ("WITHDRAWN", "取り消し済み")], default="PENDING", max_length=12)),
                ("error", models.CharField(blank=True, default="", max_length=300)),
                ("fetch_attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_attempted_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("message", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="core.operationslineinboxmessage")),
            ],
        ),
        migrations.AddIndex(model_name="operationslineinboxmessage", index=models.Index(fields=["source_id", "received_at"], name="core_opli_source_received_idx")),
        migrations.AddIndex(model_name="operationslineinboxattachment", index=models.Index(fields=["status", "created_at"], name="core_oplia_status_created_idx")),
    ]
