from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0069_store_sms_billing_exempt"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="guest_contact_phone",
            field=models.CharField(
                blank=True,
                default="",
                help_text="予約確認ページへ表示するお客様向け問い合わせ電話番号",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="store",
            name="guest_contact_phone_memo",
            field=models.CharField(
                blank=True,
                default="",
                help_text="問い合わせ電話番号の差し替え予定など、店舗内だけで確認するメモ",
                max_length=500,
            ),
        ),
    ]
