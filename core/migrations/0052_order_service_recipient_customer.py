from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0051_cast_preferred_areas"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="service_recipient_customer",
            field=models.ForeignKey(
                blank=True,
                help_text="管理者が確認して紐付けた実利用者の顧客レコード",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="service_recipient_orders",
                to="core.customer",
            ),
        ),
        migrations.CreateModel(
            name="OrderServiceRecipientLinkLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("previous_customer_id", models.PositiveIntegerField(blank=True, null=True)),
                ("previous_customer_name", models.CharField(blank=True, default="", max_length=50)),
                ("linked_customer_id", models.PositiveIntegerField(blank=True, null=True)),
                ("linked_customer_name", models.CharField(blank=True, default="", max_length=50)),
                ("executed_at", models.DateTimeField(auto_now_add=True)),
                ("executed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="executed_recipient_links", to=settings.AUTH_USER_MODEL)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="recipient_link_logs", to="core.order")),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="recipient_link_logs", to="core.store")),
            ],
            options={"ordering": ["-executed_at", "-id"]},
        ),
    ]
