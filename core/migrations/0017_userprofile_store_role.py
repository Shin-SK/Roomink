"""
UserProfile に store (FK) と role (CharField) を追加する。

3段階で安全に NOT NULL 制約を導入:
  1. store を nullable で追加 + role を追加
  2. 既存 UserProfile に Store を割り当てる (Store 0件なら fail fast)
  3. store の null=True を外す
"""

from django.db import migrations, models
import django.db.models.deletion


def populate_store(apps, schema_editor):
    Store = apps.get_model("core", "Store")
    UserProfile = apps.get_model("core", "UserProfile")

    store = Store.objects.order_by("id").first()
    if store is None:
        if UserProfile.objects.exists():
            raise RuntimeError(
                "Store が0件ですが UserProfile が存在します。"
                "migration 前に最低1件の Store を作成してください。"
            )
        # UserProfile も0件なら何もしなくて良い
        return

    UserProfile.objects.filter(store__isnull=True).update(store=store)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_user_profile"),
    ]

    operations = [
        # Step 1: nullable で store を追加 + role を追加
        migrations.AddField(
            model_name="userprofile",
            name="store",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="user_profiles",
                to="core.store",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="userprofile",
            name="role",
            field=models.CharField(
                choices=[
                    ("cast", "キャスト"),
                    ("staff", "スタッフ"),
                    ("manager", "マネージャー"),
                ],
                default="staff",
                max_length=10,
            ),
        ),
        # Step 2: 既存データに store を埋める
        migrations.RunPython(populate_store, migrations.RunPython.noop),
        # Step 3: NOT NULL にする
        migrations.AlterField(
            model_name="userprofile",
            name="store",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="user_profiles",
                to="core.store",
            ),
        ),
    ]
