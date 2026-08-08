from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0042_shiftassignment_end_day_offset"),
    ]

    operations = [
        migrations.AddField(
            model_name="shiftrequest",
            name="end_day_offset",
            field=models.PositiveSmallIntegerField(
                choices=[(0, "当日"), (1, "翌日")],
                default=0,
                help_text="終了時刻が申請日の翌日に属する場合は1",
            ),
        ),
        migrations.AddField(
            model_name="shiftrequest",
            name="approved_end_day_offset",
            field=models.PositiveSmallIntegerField(
                choices=[(0, "当日"), (1, "翌日")],
                default=0,
                help_text="承認終了時刻が承認日の翌日に属する場合は1",
            ),
        ),
    ]
