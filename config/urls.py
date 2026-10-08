from django.contrib import admin
from django.urls import include, path
from django.http import JsonResponse
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import IsAdminUser

def health(request):
    return JsonResponse({"ok": True, "service": "roomink"})

urlpatterns = [
    path("", health),
    path("healthz", health),
    path("admin/", admin.site.urls),
    path("api/health/", health),
    path("api/", include("core.urls")),
    path(
        "api/schema/",
        SpectacularAPIView.as_view(permission_classes=[IsAdminUser]),
        name="schema",
    ),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(
            url_name="schema",
            permission_classes=[IsAdminUser],
        ),
        name="swagger-ui",
    ),
]
