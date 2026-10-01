from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0072_order_timeline_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="public_booking_notification_email",
            field=models.EmailField(
                blank=True,
                default="",
                help_text="Web予約成立時の店舗向け通知先メールアドレス",
                max_length=254,
            ),
        ),
        migrations.CreateModel(
            name="OperatorNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("PUBLIC_BOOKING", "Web予約")], max_length=32)),
                ("title", models.CharField(max_length=120)),
                ("message", models.TextField(blank=True, default="")),
                ("target_path", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("order", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="operator_notifications", to="core.order")),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="operator_notifications", to="core.store")),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="OperatorNotificationReadReceipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("read_at", models.DateTimeField(auto_now_add=True)),
                ("notification", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="read_receipts", to="core.operatornotification")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="operator_notification_read_receipts", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["read_at", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="operatornotification",
            index=models.Index(fields=["store", "created_at"], name="op_notice_store_created_idx"),
        ),
        migrations.AddConstraint(
            model_name="operatornotificationreadreceipt",
            constraint=models.UniqueConstraint(fields=("notification", "user"), name="unique_operator_notification_read_receipt"),
        ),
    ]
