from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0105_legacy_customer_history")]

    operations = [
        migrations.AddField(
            model_name="castdailycheckout",
            name="pay_calculation_version",
            field=models.PositiveSmallIntegerField(
                default=2, db_default=1,
                choices=[(1, "旧計算"), (2, "延長を含む計算")],
                help_text="提出時の報酬計算方式。既存提出と旧プロセスの保存は1を保持する。",
            ),
        ),
    ]
