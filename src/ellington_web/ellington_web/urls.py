from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(url="/masters/", permanent=False)),
    path("admin/", admin.site.urls),
    path("masters/", include("ellington_web.roster.urls")),
    path("confirm/", include("ellington_web.confirmations.urls")),
]
