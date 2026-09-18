from django.db import migrations, models
import django.db.models.deletion
import core.models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0067_order_card_include_options"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrderGuestAccess",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.CharField(default=core.models.generate_order_guest_token, editable=False, max_length=32, unique=True)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("invalidated_at", models.DateTimeField(blank=True, null=True)),
                ("first_opened_at", models.DateTimeField(blank=True, null=True)),
                ("last_opened_at", models.DateTimeField(blank=True, null=True)),
                ("open_count", models.PositiveIntegerField(default=0)),
                ("last_seen_state", models.CharField(blank=True, default="", max_length=32)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("order", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="guest_access", to="core.order")),
            ],
        ),
        migrations.AddIndex(
            model_name="orderguestaccess",
            index=models.Index(fields=["expires_at", "invalidated_at"], name="core_orderg_expires_158c50_idx"),
        ),
        migrations.AddField(
            model_name="smslog",
            name="delivered_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="smslog",
            name="delivery_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="smslog",
            name="encoding",
            field=models.CharField(blank=True, default="", max_length=12),
        ),
        migrations.AddField(
            model_name="smslog",
            name="provider_status",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="smslog",
            name="segment_count",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
