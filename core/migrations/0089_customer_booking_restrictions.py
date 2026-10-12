from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0088_area_master"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="online_booking_ng",
            field=models.BooleanField(
                default=False,
                help_text="ネット予約NG。現段階では受付画面の注意表示に使用する。",
            ),
        ),
        migrations.AddField(
            model_name="customer",
            name="ng_casts",
            field=models.ManyToManyField(
                blank=True,
                help_text="個別セラピストNGの対象。flag=BAN / ban_type=CAST_NG 時に参照する。",
                related_name="ng_customers",
                to="core.cast",
            ),
        ),
    ]
