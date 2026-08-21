from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0059_cast_option_back_rate"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="card_payment_url",
            field=models.URLField(
                blank=True,
                default="",
                help_text="カード予約時に送る店舗別の共通決済URL",
                max_length=500,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="card_payment_confirmed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="card_payment_confirmed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="confirmed_card_payment_orders",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="castunavailabletime",
            name="type",
            field=models.CharField(
                choices=[
                    ("BREAK", "休憩"),
                    ("LATE", "遅刻"),
                    ("EARLY_LEAVE", "早退"),
                    ("OUT", "中抜け"),
                    ("CHANGEOVER", "入れ替え"),
                    ("STORE", "店舗都合"),
                    ("OTHER", "その他"),
                ],
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name="smstemplate",
            name="template_type",
            field=models.CharField(
                choices=[
                    ("RESERVATION_CONFIRMATION", "予約確認"),
                    ("CARD_PAYMENT_REQUEST", "カード決済前"),
                    ("CARD_PAYMENT_CONFIRMED", "カード決済完了後"),
                ],
                default="RESERVATION_CONFIRMATION",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="smslog",
            name="template_type",
            field=models.CharField(
                choices=[
                    ("RESERVATION_CONFIRMATION", "予約確認"),
                    ("CARD_PAYMENT_REQUEST", "カード決済前"),
                    ("CARD_PAYMENT_CONFIRMED", "カード決済完了後"),
                    ("RESERVATION_CANCELLED", "予約キャンセル"),
                    ("CAST_NOTICE", "キャスト通知"),
                    ("REMINDER", "リマインド"),
                    ("OTHER", "その他"),
                ],
                default="OTHER",
                max_length=32,
            ),
        ),
    ]
