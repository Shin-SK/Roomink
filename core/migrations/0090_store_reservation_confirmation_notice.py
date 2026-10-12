from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0089_customer_booking_restrictions"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="reservation_confirmation_notice",
            field=models.TextField(
                blank=True,
                default="",
                help_text="予約確定後のお客様向け予約確認URLに表示する注意事項",
            ),
        ),
    ]
