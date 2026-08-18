from django.db import migrations, models
import django.db.models.deletion
import core.models


def populate_store_slugs(apps, schema_editor):
    Store = apps.get_model("core", "Store")
    used = set()
    for store in Store.objects.order_by("id"):
        if store.name in ("Roomink本店", "東京メンズエステ"):
            value = "tokyo-mens-esthe"
            if store.name == "Roomink本店":
                store.name = "東京メンズエステ"
        elif "アールズ" in store.name:
            value = "rs-spa"
        else:
            value = f"store-{store.pk}"
        if value in used:
            value = f"{value}-{store.pk}"
        used.add(value)
        store.slug = value
        store.save(update_fields=["name", "slug"])


class Migration(migrations.Migration):
    dependencies = [("core", "0056_store_booking_notice_and_castnote_targets")]

    operations = [
        migrations.AddField(
            model_name="store",
            name="slug",
            # PostgreSQLで同一migration内のSlugField indexが重複しないよう、
            # データ投入前は通常の文字列列として追加する。
            field=models.CharField(blank=True, max_length=80, null=True),
        ),
        migrations.RunPython(populate_store_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="store",
            name="slug",
            field=models.SlugField(
                default=core.models.generate_store_slug,
                help_text="顧客向けURLに使用する店舗識別子（例: rs-spa）",
                max_length=80,
                unique=True,
            ),
        ),
        migrations.CreateModel(
            name="StoreSlugAlias",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(max_length=80, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="slug_aliases", to="core.store")),
            ],
        ),
    ]
