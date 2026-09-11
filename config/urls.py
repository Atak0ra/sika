from django.contrib import admin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import path, include
from django.views.generic import RedirectView
from django.templatetags.static import static


def sw_view(request):
    """Service Worker servi depuis la racine (scope='/')."""
    import os
    from django.conf import settings as djs
    sw_path = os.path.join(djs.BASE_DIR, 'economat', 'static', 'economat', 'js', 'sw.js')
    if not os.path.exists(sw_path):
        sw_path = os.path.join(djs.STATIC_ROOT, 'economat', 'js', 'sw.js')
    try:
        with open(sw_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        return HttpResponse('/* sw.js not found */', content_type='application/javascript')
    resp = HttpResponse(content, content_type='application/javascript')
    resp['Service-Worker-Allowed'] = '/'
    resp['Cache-Control'] = 'no-cache'
    return resp


def manifest_view(request):
    """Web App Manifest pour l'installabilité PWA."""
    manifest = {
        "name": "Sukulu \u2014 Gestion scolaire",
        "short_name": "Sukulu",
        "description": "Gestion des frais de scolarité pour les écoles d'Afrique de l'Ouest.",
        "start_url": "/eco/ecoles/",
        "display": "standalone",
        "background_color": "#fbfbfd",
        "theme_color": "#4f46e5",
        "lang": "fr",
        "icons": [
            {"src": "/static/economat/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/static/economat/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
    }
    return JsonResponse(manifest)


def offline_view(request):
    """Page fallback offline."""
    return render(request, 'economat/offline.html', status=200)


urlpatterns = [
    path("admin/", admin.site.urls),
    # ── PWA (scope racine obligatoire pour le SW)
    path("sw.js",                sw_view,       name="service_worker"),
    path("manifest.webmanifest", manifest_view, name="web_manifest"),
    path("offline.html",         offline_view,  name="offline"),
    # ── App principale
    path("eco/", include("economat.urls")),
    path("", RedirectView.as_view(url="/eco/", permanent=False), name="home"),
]
