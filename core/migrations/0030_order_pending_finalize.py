from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0029_customer_merge_log"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("REQUESTED", "リクエスト"),
                    ("CONFIRMED", "確定"),
                    ("IN_PROGRESS", "施術中"),
                    ("PENDING_FINALIZE", "会計待ち"),
                    ("DONE", "完了"),
                    ("CANCELLED", "キャンセル"),
                ],
                default="REQUESTED",
                max_length=20,
            ),
        ),
    ]
