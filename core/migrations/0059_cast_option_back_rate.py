from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


def copy_fullback_to_rate(apps, schema_editor):
    Cast = apps.get_model("core", "Cast")
    Cast.objects.filter(option_fullback_enabled=True).update(option_back_rate=100)


def copy_rate_to_fullback(apps, schema_editor):
    Cast = apps.get_model("core", "Cast")
    Cast.objects.update(option_fullback_enabled=False)
    Cast.objects.filter(option_back_rate=100).update(option_fullback_enabled=True)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0058_alter_cast_unique_together"),
    ]

    operations = [
        migrations.AddField(
            model_name="cast",
            name="option_back_rate",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="オプションバック率（%）",
                validators=[MinValueValidator(0), MaxValueValidator(100)],
            ),
        ),
        migrations.RunPython(copy_fullback_to_rate, copy_rate_to_fullback),
    ]
