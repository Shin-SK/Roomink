import secrets

from django.db import migrations, models


def populate_webhook_tokens(apps, schema_editor):
    Store = apps.get_model("core", "Store")
    for store in Store.objects.all():
        store.line_webhook_token = secrets.token_hex(16)
        store.save(update_fields=["line_webhook_token"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_store_line_add_friend_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="store",
            name="line_channel_secret",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="store",
            name="line_channel_access_token",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="store",
            name="line_is_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="store",
            name="line_webhook_token",
            field=models.CharField(
                blank=True, default="", max_length=64,
                help_text="webhook URL に埋め込む store 識別トークン",
            ),
        ),
        migrations.RunPython(populate_webhook_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="store",
            name="line_webhook_token",
            field=models.CharField(
                blank=True, default="", max_length=64, unique=True,
                help_text="webhook URL に埋め込む store 識別トークン",
            ),
        ),
    ]
