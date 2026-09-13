from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0066_order_cancelled_by_order_created_by_order_updated_by"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="card_include_options",
            field=models.BooleanField(
                default=False,
                help_text="カード決済額にオプション代を含めるか（Falseの場合はオプション代を現金で受領）",
            ),
        ),
    ]
