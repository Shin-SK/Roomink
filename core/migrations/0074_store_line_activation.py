from django.db import migrations, models
from django.utils import timezone


def mark_existing_line_stores_active(apps, schema_editor):
    """既存稼働店舗を維持し、フラッグシップだけ店舗の開始待ちへ移行する。"""
    Store = apps.get_model("core", "Store")
    now = timezone.now()
    Store.objects.filter(line_is_enabled=True).update(
        line_setup_completed_at=now,
        line_started_at=now,
    )
    # 今回接続したフラッグシップは、店舗が開始ボタンを押すまで送信を始めない。
    Store.objects.filter(slug="flagship", line_is_enabled=True).update(
        line_started_at=None,
    )


def clear_line_activation(apps, schema_editor):
    Store = apps.get_model("core", "Store")
    Store.objects.update(
        line_setup_completed_at=None,
        line_started_at=None,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0073_public_booking_notifications"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="line_setup_completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="store",
            name="line_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(mark_existing_line_stores_active, clear_line_activation),
    ]
