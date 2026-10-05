from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0075_operationslinecontact_operationscase_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="operationslinecontact",
            name="registration_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="operationslinecontact",
            name="registration_requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="operationslinecontact",
            name="registration_slack_channel_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="operationslinecontact",
            name="registration_slack_thread_ts",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="operationscase",
            name="codex_thread_id",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="operationscase",
            name="codex_thread_url",
            field=models.URLField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="operationscase",
            name="codex_worktree_path",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="operationscase",
            name="codex_dispatch_action",
            field=models.CharField(choices=[("NONE", "なし"), ("CREATE_THREAD", "案件スレッド作成"), ("START_WORK", "修正開始")], default="NONE", max_length=20),
        ),
        migrations.AddField(
            model_name="operationscase",
            name="codex_dispatch_status",
            field=models.CharField(choices=[("NONE", "なし"), ("PENDING", "起動待ち"), ("CLAIMED", "起動中"), ("SUCCEEDED", "完了"), ("FAILED", "失敗")], default="NONE", max_length=12),
        ),
        migrations.AddField(
            model_name="operationscase",
            name="codex_dispatch_error",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="operationscase",
            name="codex_dispatch_requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="operationscase",
            name="codex_dispatch_claimed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="operationscase",
            name="codex_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
