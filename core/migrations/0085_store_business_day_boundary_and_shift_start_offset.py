from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0084_shiftassignment_room_optional"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="business_day_boundary_hour",
            field=models.PositiveSmallIntegerField(
                default=5,
                help_text="この時刻から次の営業日として扱う（例: 5=29:00まで前営業日）",
                validators=[MinValueValidator(0), MaxValueValidator(5)],
            ),
        ),
        migrations.AddField(
            model_name="shiftassignment",
            name="start_day_offset",
            field=models.PositiveSmallIntegerField(
                choices=[(0, "当日"), (1, "翌日")],
                default=0,
                help_text="開始時刻がシフト日の翌日に属する場合は1",
            ),
        ),
    ]
