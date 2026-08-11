from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0050_publicbookingverification"),
    ]

    operations = [
        migrations.AddField(
            model_name="cast",
            name="preferred_area_1",
            field=models.CharField(blank=True, default="", help_text="希望エリア 第1希望", max_length=50),
        ),
        migrations.AddField(
            model_name="cast",
            name="preferred_area_2",
            field=models.CharField(blank=True, default="", help_text="希望エリア 第2希望", max_length=50),
        ),
        migrations.AddField(
            model_name="cast",
            name="preferred_area_3",
            field=models.CharField(blank=True, default="", help_text="希望エリア 第3希望", max_length=50),
        ),
        migrations.AddField(
            model_name="cast",
            name="preferred_area_4",
            field=models.CharField(blank=True, default="", help_text="希望エリア 第4希望", max_length=50),
        ),
        migrations.AddField(
            model_name="cast",
            name="preferred_area_5",
            field=models.CharField(blank=True, default="", help_text="希望エリア 第5希望", max_length=50),
        ),
    ]
