import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.models import Store, UserProfile
from core.services.cast_user import create_staff_with_user


class Command(BaseCommand):
    help = "店舗slugを指定して、初回マネージャーアカウントを安全に発行します。"

    def add_arguments(self, parser):
        parser.add_argument("--store-slug", required=True)
        parser.add_argument("--username", required=True)
        parser.add_argument("--email", default="")

    def handle(self, *args, **options):
        store = Store.resolve_slug(options["store_slug"])
        if store is None:
            raise CommandError("指定した店舗が見つかりません。")

        User = get_user_model()
        username = options["username"].strip()
        if not username:
            raise CommandError("ユーザー名を入力してください。")
        if User.objects.filter(username=username).exists():
            raise CommandError("このユーザー名はすでに使用されています。")

        temporary_password = secrets.token_urlsafe(18)
        profile = create_staff_with_user(
            store=store,
            username=username,
            password=temporary_password,
            email=options["email"].strip(),
            role=UserProfile.Role.MANAGER,
        )
        self.stdout.write(self.style.SUCCESS("店舗マネージャーを作成しました。"))
        self.stdout.write(f"store={profile.store.name} ({profile.store.slug})")
        self.stdout.write(f"username={profile.user.username}")
        self.stdout.write(f"temporary_password={temporary_password}")
        self.stdout.write("初回ログイン後にパスワードを変更してください。")
