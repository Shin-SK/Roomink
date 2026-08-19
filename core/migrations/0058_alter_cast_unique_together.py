from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0057_store_slug_and_alias"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="cast",
            unique_together=set(),
        ),
    ]
