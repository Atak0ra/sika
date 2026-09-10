from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),

    # ── Économat scolaire (SaaS principal)
    path("eco/", include("economat.urls")),

    # ── / → landing de l'économat
    path("", RedirectView.as_view(url="/eco/", permanent=False), name="home"),
]
