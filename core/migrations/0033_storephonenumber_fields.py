from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0032_stage_b1"),
    ]

    operations = [
        migrations.AddField(
            model_name="storephonenumber",
            name="source_phone",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.AddField(
            model_name="storephonenumber",
            name="memo",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="storephonenumber",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="storephonenumber",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name="storephonenumber",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
    ]
