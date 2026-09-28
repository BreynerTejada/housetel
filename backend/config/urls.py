from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

# `/api/schema/` and `/api/docs/` follow SPECTACULAR_SETTINGS["SERVE_PERMISSIONS"] (public in development,
# staff-only in production). `/django-admin/` exists only with ADMIN_ENABLED (and, in production, only for
# signed-in staff: apps.core.middleware.AdminGateMiddleware).
urlpatterns = [
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]
if settings.ADMIN_ENABLED:
    urlpatterns.insert(0, path("django-admin/", admin.site.urls))
for app in settings.LOCAL_APPS:
    urlpatterns += [
        path(f"api/v1/public/{app}/", include(f"apps.{app}.public_urls")),
        path(f"api/v1/{app}/", include(f"apps.{app}.urls")),
    ]
# Development only (the helper is a no-op without DEBUG): in production nginx serves the public media
# (/media/photos|branding|booking-engine/) and never the private files, which live outside MEDIA_ROOT.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
