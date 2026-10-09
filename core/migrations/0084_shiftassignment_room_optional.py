from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0083_roomink_work_devices"),
    ]

    operations = [
        migrations.AlterField(
            model_name="shiftassignment",
            name="room",
            field=models.ForeignKey(
                blank=True,
                help_text="未定のまま登録し、必要になった時点で割り当てる",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="shift_assignments",
                to="core.room",
            ),
        ),
    ]
