import unicodedata

from django.db import migrations, models
import django.db.models.deletion


def normalize(value):
    return unicodedata.normalize("NFKC", value or "").strip().casefold()


def create_area_masters(apps, schema_editor):
    Area = apps.get_model("core", "Area")
    Room = apps.get_model("core", "Room")
    Cast = apps.get_model("core", "Cast")
    Preference = apps.get_model("core", "CastAreaPreference")

    # Preserve every distinct legacy label. We intentionally do not fuzzy-merge
    # similar names: a manager must make that decision explicitly after migration.
    areas = {}
    def area_for(store_id, legacy_name):
        label = (legacy_name or "").strip()
        key = (store_id, normalize(label))
        if not label:
            return None
        if key not in areas:
            area, _ = Area.objects.get_or_create(
                store_id=store_id,
                normalized_name=key[1],
                defaults={"name": label},
            )
            areas[key] = area
        return areas[key]

    for room in Room.objects.exclude(area_name="").iterator():
        area = area_for(room.store_id, room.area_name)
        if area:
            room.area_id = area.id
            room.save(update_fields=["area"])

    for cast in Cast.objects.iterator():
        assigned_area_ids = set()
        for rank in range(1, 6):
            area = area_for(cast.store_id, getattr(cast, f"preferred_area_{rank}", ""))
            if area and area.id not in assigned_area_ids:
                Preference.objects.get_or_create(cast_id=cast.id, rank=rank, defaults={"area_id": area.id})
                assigned_area_ids.add(area.id)


def reverse_area_masters(apps, schema_editor):
    # The legacy strings remain intentionally; reversing only removes new links.
    Room = apps.get_model("core", "Room")
    Preference = apps.get_model("core", "CastAreaPreference")
    Room.objects.update(area=None)
    Preference.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0087_alter_linenotificationlog_notification_type")]

    operations = [
        migrations.CreateModel(
            name="Area",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=50)),
                ("normalized_name", models.CharField(editable=False, max_length=100)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="areas", to="core.store")),
            ],
            options={"ordering": ("sort_order", "name", "id")},
        ),
        migrations.AddConstraint(
            model_name="area",
            constraint=models.UniqueConstraint(fields=("store", "normalized_name"), name="core_area_store_normalized_name_unique"),
        ),
        migrations.AddField(
            model_name="room",
            name="area",
            field=models.ForeignKey(blank=True, help_text="店舗のエリアマスタから選択する。", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="rooms", to="core.area"),
        ),
        migrations.CreateModel(
            name="CastAreaPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("rank", models.PositiveSmallIntegerField()),
                ("area", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="cast_preferences", to="core.area")),
                ("cast", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="area_preferences", to="core.cast")),
            ],
            options={"ordering": ("rank", "id")},
        ),
        migrations.AddConstraint(
            model_name="castareapreference",
            constraint=models.UniqueConstraint(fields=("cast", "rank"), name="core_cast_area_preference_rank_unique"),
        ),
        migrations.AddConstraint(
            model_name="castareapreference",
            constraint=models.UniqueConstraint(fields=("cast", "area"), name="core_cast_area_preference_area_unique"),
        ),
        migrations.AddField(
            model_name="shiftassignment",
            name="requested_area",
            field=models.ForeignKey(blank=True, help_text="運営が指定した割当希望エリア。空欄はキャスト希望順で判定する。", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="shift_assignments", to="core.area"),
        ),
        migrations.RunPython(create_area_masters, reverse_area_masters),
    ]
