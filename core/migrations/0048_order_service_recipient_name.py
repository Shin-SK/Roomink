from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0047_alter_order_room"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="service_recipient_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="実際の利用者名。空欄は連絡者本人として扱う",
                max_length=50,
            ),
        ),
    ]
