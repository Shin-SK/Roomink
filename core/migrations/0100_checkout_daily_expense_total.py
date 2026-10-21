from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0099_order_sales_area_history")]

    operations = [
        migrations.AddField(
            model_name="castdailycheckout",
            name="daily_expense_total",
            field=models.PositiveIntegerField(
                null=True, blank=True, db_default=None,
                help_text="退勤提出時の個別雑費。旧提出はNULLのまま保持する。",
            ),
        ),
    ]
