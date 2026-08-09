from django.db import migrations, models


def backfill_extension_duration(apps, schema_editor):
    Order = apps.get_model("core", "Order")
    for order in Order.objects.exclude(extension_id=None).select_related("extension").iterator():
        order.extension_duration = order.extension.duration
        order.save(update_fields=["extension_duration"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0044_room_address"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="extension_duration",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(backfill_extension_duration, migrations.RunPython.noop),
    ]
