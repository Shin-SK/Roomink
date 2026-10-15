from django.db import migrations, models


def enable_confirmed_policy(apps, schema_editor):
    # Confirmed by the flagship operator on 2026-10-15. Other stores retain
    # their existing allocation; settled snapshots are never rewritten.
    apps.get_model("core", "Store").objects.using(schema_editor.connection.alias).filter(
        slug="flagship",
    ).update(nomination_fullback_enabled=True)


class Migration(migrations.Migration):
    dependencies = [("core", "0093_line_registration_session")]
    operations = [
        migrations.AddField(
            model_name="store", name="nomination_fullback_enabled",
            field=models.BooleanField(default=False, help_text="指名料を種類に関わらず全額キャストへバックする"),
        ),
        migrations.RunPython(enable_confirmed_policy, migrations.RunPython.noop),
    ]
