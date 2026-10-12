from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0091_castcustomermemo"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="shift_request_start_hour",
            field=models.PositiveSmallIntegerField(
                default=11,
                help_text="キャストがシフト申請で選択できる最も早い開始時刻",
                validators=[MinValueValidator(0), MaxValueValidator(23)],
            ),
        ),
    ]
