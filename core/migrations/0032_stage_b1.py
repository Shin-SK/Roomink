from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0031_shiftassignment_clocked_in_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='room',
            name='background_color',
            field=models.CharField(blank=True, default='', help_text='HEX形式 例: #fde2e4', max_length=7),
        ),
        migrations.AddField(
            model_name='shiftassignment',
            name='daily_memo',
            field=models.TextField(blank=True, default='', help_text='その日だけのメモ'),
        ),
        migrations.AddField(
            model_name='shiftassignment',
            name='is_absent',
            field=models.BooleanField(default=False, help_text='当欠フラグ'),
        ),
    ]
