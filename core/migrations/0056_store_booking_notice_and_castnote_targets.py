from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0055_customer_email"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="public_booking_notice",
            field=models.TextField(
                blank=True,
                default="",
                help_text="店舗別のWeb予約画面へ表示する注意事項",
            ),
        ),
        migrations.AddField(
            model_name="castnote",
            name="image_urls",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="ノートへ添付する画像URL（表示順）",
            ),
        ),
        migrations.AddField(
            model_name="castnote",
            name="target_casts",
            field=models.ManyToManyField(
                blank=True,
                help_text="指定なしの場合は全キャストへ公開",
                related_name="targeted_notes",
                to="core.cast",
            ),
        ),
    ]
