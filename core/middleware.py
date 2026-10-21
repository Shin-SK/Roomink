"""Ingress checks that run before Roomink handles an API request."""

from secrets import compare_digest

from django.conf import settings
from django.http import JsonResponse
from django.utils.cache import add_never_cache_headers


class ApiNoStoreMiddleware:
    """API responses are dynamic and may contain tenant- or user-private data.

    Cover success and denial responses, including CSV downloads whose file
    extension otherwise makes them eligible for shared edge caching.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path_info.startswith("/api/"):
            add_never_cache_headers(response)
            response["CDN-Cache-Control"] = "no-store"
            response["Cloudflare-CDN-Cache-Control"] = "no-store"
        return response


class CloudflareOriginLockMiddleware:
    """Require the secret header Cloudflare adds before forwarding to Heroku.

    Heroku's shared router keeps its ``*.herokuapp.com`` address reachable.
    Requiring a value which only Cloudflare injects prevents that address from
    bypassing Cloudflare's edge protections. The value is never stored in code.
    """

    header_name = "HTTP_X_ROOMINK_ORIGIN_SECRET"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.CLOUDFLARE_ORIGIN_LOCK_ENABLED:
            supplied = request.META.get(self.header_name, "")
            expected = settings.CLOUDFLARE_ORIGIN_SECRET
            if not compare_digest(supplied, expected):
                return JsonResponse(
                    {"detail": "Origin access is restricted."},
                    status=403,
                )
        return self.get_response(request)
