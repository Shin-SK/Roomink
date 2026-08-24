from django.db import migrations, models


def seed_cast_note_sort_order(apps, schema_editor):
    CastNote = apps.get_model("core", "CastNote")
    store_ids = CastNote.objects.values_list("store_id", flat=True).distinct()
    for store_id in store_ids:
        note_ids = CastNote.objects.filter(store_id=store_id).order_by(
            "-is_pinned",
            "-published_at",
            "-created_at",
            "pk",
        ).values_list("pk", flat=True)
        for index, note_id in enumerate(note_ids, start=1):
            CastNote.objects.filter(pk=note_id).update(sort_order=index * 10)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0061_seed_store_card_payment_urls"),
    ]

    operations = [
        migrations.AddField(
            model_name="castnote",
            name="sort_order",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(seed_cast_note_sort_order, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name="castnote",
            options={"ordering": ["-is_pinned", "sort_order", "pk"]},
        ),
    ]
