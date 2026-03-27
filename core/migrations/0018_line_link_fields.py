import secrets
import string

from django.db import migrations, models

import core.models


def generate_unique_codes(apps, schema_editor):
    """既存 Cast に一意な連携コードを割り当てる"""
    Cast = apps.get_model("core", "Cast")
    alphabet = string.ascii_uppercase + string.digits
    used = set()
    for cast in Cast.objects.all():
        while True:
            code = "".join(secrets.choice(alphabet) for _ in range(6))
            if code not in used:
                break
        used.add(code)
        cast.line_link_code = code
        cast.save(update_fields=["line_link_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0017_userprofile_store_role"),
    ]

    operations = [
        # 1) Add fields without unique constraint first
        migrations.AddField(
            model_name="cast",
            name="line_user_id",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="cast",
            name="line_link_code",
            field=models.CharField(blank=True, max_length=8, null=True),
        ),
        migrations.AddField(
            model_name="cast",
            name="line_linked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        # 2) Generate unique codes for existing rows
        migrations.RunPython(generate_unique_codes, migrations.RunPython.noop),
        # 3) Now add unique constraint + default
        migrations.AlterField(
            model_name="cast",
            name="line_link_code",
            field=models.CharField(
                blank=True, default=core.models.generate_line_link_code,
                max_length=8, null=True, unique=True,
            ),
        ),
    ]
