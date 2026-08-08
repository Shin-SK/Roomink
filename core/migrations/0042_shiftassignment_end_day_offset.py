from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0041_customer_account_invitation"),
    ]

    operations = [
        migrations.AddField(
            model_name="shiftassignment",
            name="end_day_offset",
            field=models.PositiveSmallIntegerField(
                choices=[(0, "当日"), (1, "翌日")],
                default=0,
                help_text="終了時刻がシフト日の翌日に属する場合は1",
            ),
        ),
    ]
