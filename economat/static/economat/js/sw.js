/**
 * sw.js — Service Worker SikaSkool
 * =================================
 * Stratégie : Network-first avec fallback cache.
 *   - Pages navigables → réseau d'abord, cache si offline
 *   - Assets statiques → cache-first (versionnés)
 *   - API/JSON → réseau uniquement (pas de cache des données)
 *   - Page fallback offline si ressource jamais visitée
 *
 * Scope : / (racine, défini dans sw_view Django)
 */

var CACHE_SHELL   = 'sukulu-shell-v1';
var CACHE_PAGES   = 'sukulu-pages-v1';

/* Assets shell : mis en cache à l'install, toujours disponibles */
var SHELL_ASSETS = [
  '/offline.html',
  'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap',
];

/* ── Install : cache le shell ──────────────────────────────────────────────── */
self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE_SHELL).then(function (cache) {
      return cache.addAll(SHELL_ASSETS);
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

/* ── Activate : nettoie les vieux caches ──────────────────────────────────── */
self.addEventListener('activate', function (e) {
  var keep = [CACHE_SHELL, CACHE_PAGES];
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (k) { return keep.indexOf(k) === -1; })
            .map(function (k) { return caches.delete(k); })
      );
    }).then(function () { return self.clients.claim(); })
  );
});

/* ── Fetch : stratégie par type de requête ─────────────────────────────────── */
self.addEventListener('fetch', function (e) {
  var req = e.request;
  var url = new URL(req.url);

  /* 1. Requêtes non-GET (POST sync, encaissement) → réseau direct */
  if (req.method !== 'GET') return;

  /* 2. Chrome extensions, other origins → ignore */
  if (url.origin !== location.origin) return;

  /* 3. API JSON (student_search, sync) → réseau uniquement */
  if (url.pathname.startsWith('/econome/api/') ||
      url.pathname.startsWith('/econome/sync/')) {
    return;
  }

  /* 4. Fichiers statiques → cache-first */
  if (url.pathname.startsWith('/static/') ||
      url.pathname.startsWith('/staticfiles/')) {
    e.respondWith(
      caches.match(req).then(function (cached) {
        if (cached) return cached;
        return fetch(req).then(function (resp) {
          if (resp && resp.status === 200) {
            var clone = resp.clone();
            caches.open(CACHE_SHELL).then(function (c) { c.put(req, clone); });
          }
          return resp;
        });
      })
    );
    return;
  }

  /* 5. Pages navigables → Network-first, fallback cache, fallback /offline.html */
  e.respondWith(
    fetch(req).then(function (resp) {
      if (resp && resp.status === 200) {
        var clone = resp.clone();
        caches.open(CACHE_PAGES).then(function (c) { c.put(req, clone); });
      }
      return resp;
    }).catch(function () {
      return caches.match(req).then(function (cached) {
        return cached || caches.match('/offline.html');
      });
    })
  );
});
