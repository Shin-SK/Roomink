from django.db import migrations


CARD_PAYMENT_URLS = {
    "tokyo-mens-esthe": "https://pay2.star-pay.jp/site/smt/shop.php?payc=A8496",
    "rs-spa": "https://pay2.star-pay.jp/site/smt/shop.php?payc=A20254",
}


def set_card_payment_urls(apps, schema_editor):
    Store = apps.get_model("core", "Store")
    for slug, url in CARD_PAYMENT_URLS.items():
        Store.objects.filter(slug=slug).update(card_payment_url=url)


def clear_seeded_card_payment_urls(apps, schema_editor):
    Store = apps.get_model("core", "Store")
    for slug, url in CARD_PAYMENT_URLS.items():
        Store.objects.filter(slug=slug, card_payment_url=url).update(
            card_payment_url="",
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0060_alter_castunavailabletime_type"),
    ]

    operations = [
        migrations.RunPython(
            set_card_payment_urls,
            clear_seeded_card_payment_urls,
        ),
    ]
