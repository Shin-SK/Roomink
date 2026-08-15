from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Customer, SmsLog, Store, UserProfile


User = get_user_model()


class CustomerCsvImportTest(TestCase):
    def setUp(self):
        self.store = Store.objects.create(name="CSVテスト店舗")
        self.manager = User.objects.create_user("csv_manager")
        UserProfile.objects.create(
            user=self.manager,
            store=self.store,
            role=UserProfile.Role.MANAGER,
        )
        self.staff = User.objects.create_user("csv_staff")
        UserProfile.objects.create(
            user=self.staff,
            store=self.store,
            role=UserProfile.Role.STAFF,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def upload(self, text, *, preview=False, encoding="utf-8-sig"):
        suffix = "&preview=1" if preview else ""
        file_obj = SimpleUploadedFile(
            "customers.csv",
            text.encode(encoding),
            content_type="text/csv",
        )
        return self.client.post(
            f"/api/op/csv-import/?model=customer{suffix}",
            {"file": file_obj},
            format="multipart",
        )

    def test_template_download_has_japanese_customer_headers(self):
        response = self.client.get("/api/op/csv-import/template/?model=customer")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8-sig")
        self.assertEqual(
            content.strip(),
            "名前,電話番号,メールアドレス,利用履歴,顧客メモ,運営メモ,フラグ,出禁種別",
        )

    def test_japanese_headers_preview_and_import_customer_fields(self):
        text = (
            "名前,電話番号,メールアドレス,利用履歴,顧客メモ,運営メモ,フラグ,出禁種別\n"
            '山田太郎,090-1234-5678,taro@example.com,"2025/1/2 コース90分 30,000円\n'
            '2025/2/3 コース120分 40,000円",共有メモ,運営だけのメモ,出禁,店出禁\n'
        )

        preview = self.upload(text, preview=True)
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.json()["can_import"])
        self.assertEqual(preview.json()["errors"], [])

        response = self.upload(text)
        self.assertEqual(response.status_code, 200)
        customer = Customer.objects.get(store=self.store, phone="09012345678")
        self.assertEqual(customer.display_name, "山田太郎")
        self.assertEqual(customer.email, "taro@example.com")
        self.assertIn("2025/1/2", customer.legacy_usage_history)
        self.assertIn("2025/2/3", customer.legacy_usage_history)
        self.assertEqual(customer.memo, "共有メモ")
        self.assertEqual(customer.staff_memo, "運営だけのメモ")
        self.assertEqual(customer.flag, Customer.Flag.BAN)
        self.assertEqual(customer.ban_type, Customer.BanType.STORE_BAN)
        self.assertIsNone(customer.user)
        self.assertEqual(SmsLog.objects.count(), 0)

    def test_cp932_csv_is_supported(self):
        text = "名前,電話番号,備考,フラグ\n佐藤花子,08012345678,旧システム備考,要注意\n"

        preview = self.upload(text, preview=True, encoding="cp932")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["encoding"], "cp932")

        response = self.upload(text, encoding="cp932")
        self.assertEqual(response.status_code, 200)
        customer = Customer.objects.get(phone="08012345678")
        self.assertEqual(customer.staff_memo, "旧システム備考")
        self.assertEqual(customer.flag, Customer.Flag.ATTENTION)

    def test_invalid_row_does_not_update_database(self):
        text = "名前,電話番号,メールアドレス\n不正データ,123,not-an-email\n"

        preview = self.upload(text, preview=True)
        self.assertEqual(preview.status_code, 200)
        self.assertFalse(preview.json()["can_import"])
        self.assertGreaterEqual(len(preview.json()["errors"]), 1)

        response = self.upload(text)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Customer.objects.exists())

    def test_duplicate_phone_in_same_file_is_rejected(self):
        text = "名前,電話番号\n顧客A,07012345678\n顧客B,070-1234-5678\n"

        preview = self.upload(text, preview=True)
        self.assertEqual(preview.status_code, 200)
        self.assertFalse(preview.json()["can_import"])
        self.assertIn("重複", preview.json()["errors"][0]["message"])

    def test_blank_optional_columns_do_not_clear_existing_customer(self):
        customer = Customer.objects.create(
            store=self.store,
            phone="09000000001",
            display_name="既存顧客",
            email="old@example.com",
            legacy_usage_history="既存履歴",
            flag=Customer.Flag.BAN,
            ban_type=Customer.BanType.STORE_BAN,
            staff_memo="既存メモ",
        )
        text = "名前,電話番号,メールアドレス,利用履歴,運営メモ,フラグ,出禁種別\n更新名,09000000001,,,,,\n"

        response = self.upload(text)
        self.assertEqual(response.status_code, 200)
        customer.refresh_from_db()
        self.assertEqual(customer.display_name, "更新名")
        self.assertEqual(customer.email, "old@example.com")
        self.assertEqual(customer.legacy_usage_history, "既存履歴")
        self.assertEqual(customer.staff_memo, "既存メモ")
        self.assertEqual(customer.flag, Customer.Flag.BAN)
        self.assertEqual(customer.ban_type, Customer.BanType.STORE_BAN)

    def test_staff_cannot_download_template_or_import(self):
        self.client.force_authenticate(self.staff)

        template = self.client.get("/api/op/csv-import/template/?model=customer")
        imported = self.upload("名前,電話番号\n顧客,09012345678\n")

        self.assertEqual(template.status_code, 403)
        self.assertEqual(imported.status_code, 403)
        self.assertFalse(Customer.objects.exists())
