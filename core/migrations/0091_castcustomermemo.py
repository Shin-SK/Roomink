from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0090_store_reservation_confirmation_notice"),
    ]

    operations = [
        migrations.CreateModel(
            name="CastCustomerMemo",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("memo", models.TextField(blank=True, default="")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "cast",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="customer_memos",
                        to="core.cast",
                    ),
                ),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cast_memos",
                        to="core.customer",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="castcustomermemo",
            constraint=models.UniqueConstraint(
                fields=("cast", "customer"),
                name="core_cast_customer_memo_unique",
            ),
        ),
    ]
