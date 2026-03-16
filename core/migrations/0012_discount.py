from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_nominationfee'),
    ]

    operations = [
        migrations.CreateModel(
            name='Discount',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50)),
                ('discount_type', models.CharField(
                    choices=[('fixed', '固定額'), ('percent', 'パーセント')],
                    default='fixed',
                    max_length=10,
                )),
                ('value', models.PositiveIntegerField()),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('store', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='discounts', to='core.store')),
            ],
            options={
                'ordering': ('sort_order', 'id'),
            },
        ),
    ]
