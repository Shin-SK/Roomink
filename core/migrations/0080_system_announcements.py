from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0079_castofficecashreceipt"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SystemAnnouncement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=120)),
                ("body", models.TextField()),
                ("kind", models.CharField(choices=[("UPDATE", "アップデート"), ("IMPORTANT", "重要"), ("MAINTENANCE", "メンテナンス")], default="UPDATE", max_length=16)),
                ("audience", models.CharField(choices=[("ALL", "全ユーザー"), ("OPERATORS", "マネージャー・スタッフ"), ("MANAGERS", "マネージャー"), ("STAFF", "スタッフ"), ("CASTS", "キャスト"), ("CUSTOMERS", "顧客")], default="ALL", max_length=16)),
                ("target_path", models.CharField(blank=True, default="", help_text="Roomink内の移動先。例: /account/security", max_length=255)),
                ("published_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_system_announcements", to=settings.AUTH_USER_MODEL)),
                ("target_stores", models.ManyToManyField(blank=True, help_text="指定なしの場合は全店舗へ配信します。", related_name="system_announcements", to="core.store")),
            ],
            options={
                "ordering": ["-published_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="SystemAnnouncementReadReceipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("read_at", models.DateTimeField(auto_now_add=True)),
                ("announcement", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="read_receipts", to="core.systemannouncement")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="system_announcement_read_receipts", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["read_at", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="systemannouncement",
            index=models.Index(fields=["is_active", "published_at"], name="sys_notice_active_pub_idx"),
        ),
        migrations.AddConstraint(
            model_name="systemannouncementreadreceipt",
            constraint=models.UniqueConstraint(fields=("announcement", "user"), name="unique_system_announcement_read_receipt"),
        ),
    ]
