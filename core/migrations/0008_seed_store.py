from django.db import migrations


def seed_store(apps, schema_editor):
    Store = apps.get_model("core", "Store")
    if not Store.objects.exists():
        Store.objects.create(name="Roomink本店")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_shift_request"),
    ]

    operations = [
        migrations.RunPython(seed_store, migrations.RunPython.noop),
    ]
