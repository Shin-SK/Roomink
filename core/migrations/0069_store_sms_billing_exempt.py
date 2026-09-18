from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0068_orderguestaccess_sms_delivery_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="sms_billing_exempt",
            field=models.BooleanField(
                default=False,
                help_text="検証店舗など、SMS利用量は計測するが月額課金の対象外とする店舗",
            ),
        ),
    ]
