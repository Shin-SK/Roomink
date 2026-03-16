from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_order_addons'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='medium',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='orders',
                to='core.medium',
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='medium_name',
            field=models.CharField(default='', max_length=50),
        ),
    ]
