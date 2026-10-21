from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase

from core.middleware import ApiNoStoreMiddleware
from core import test_sales_allocation


class ApiCacheMiddlewareTest(SimpleTestCase):
    def test_success_denial_and_existing_public_headers_cannot_be_shared(self):
        for status in (200, 302, 400, 403, 404, 500):
            with self.subTest(status=status):
                response = HttpResponse(status=status, content_type="text/csv")
                response["Cache-Control"] = "public, max-age=14400"
                middleware = ApiNoStoreMiddleware(lambda request: response)
                result = middleware(RequestFactory().get("/api/op/sales-dashboard-export.csv"))
                for token in ("private", "no-store", "no-cache", "max-age=0"):
                    self.assertIn(token, result["Cache-Control"])
                self.assertNotIn("public", result["Cache-Control"])
                self.assertEqual(result["CDN-Cache-Control"], "no-store")
                self.assertEqual(result["Cloudflare-CDN-Cache-Control"], "no-store")

    def test_static_assets_keep_their_cache_policy(self):
        response = HttpResponse()
        response["Cache-Control"] = "public, max-age=31536000, immutable"
        result = ApiNoStoreMiddleware(lambda request: response)(RequestFactory().get("/assets/app.js"))
        self.assertEqual(result["Cache-Control"], "public, max-age=31536000, immutable")


class ApiCacheIntegrationTest(TestCase):
    setUp = test_sales_allocation.SalesAllocationTest.setUp

    def test_csv_json_and_permission_denial_all_prohibit_caching(self):
        paths = (
            f"/api/op/sales-dashboard-export.csv?date_from={self.day}&date_to={self.day}",
            f"/api/op/daily-settlement/export/?date={self.day}",
            f"/api/op/sales-dashboard/?date_from={self.day}&date_to={self.day}",
        )
        for client, expected in ((self.manager_client, 200), (self.cast_client, 403)):
            for path in paths:
                with self.subTest(path=path, status=expected):
                    response = client.get(path)
                    self.assertEqual(response.status_code, expected)
                    self.assertIn("no-store", response["Cache-Control"])
                    self.assertIn("private", response["Cache-Control"])
                    self.assertEqual(response["Cloudflare-CDN-Cache-Control"], "no-store")
