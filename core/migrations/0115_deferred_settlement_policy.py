from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0114_classify_linked_free_booking_queues")]
    operations = [
        migrations.AddField(
            model_name="store", name="deferred_settlement_from",
            field=models.DateField(blank=True, null=True,
                help_text="後日経理確認方式の開始営業日。未設定なら従来方式を継続。"),
        ),
        migrations.AddField(
            model_name="castdailycheckout", name="cash_handover_recorded",
            field=models.BooleanField(default=True, db_default=True,
                help_text="実受渡の記録を含むか。後日確認方式の退勤チェックはFalse。"),
        ),
    ]
