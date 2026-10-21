from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0100_checkout_daily_expense_total")]

    operations = [
        migrations.AddField(
            model_name="shiftrequest",
            name=name,
            field=models.PositiveSmallIntegerField(choices=[(0, "当日"), (1, "翌日")], default=0),
        )
        for name in ("start_day_offset", "approved_start_day_offset")
    ]
