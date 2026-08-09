from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0046_cast_unavailable_time"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="room",
            field=models.ForeignKey(
                blank=True,
                help_text="シフト外予約では未定のまま保存し、シフト登録時に割り当てる",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="orders",
                to="core.room",
            ),
        ),
    ]
