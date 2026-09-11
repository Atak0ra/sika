/**
 * auth-offline.js — Authentification offline PWA (SikaSkool)
 *
 * Deux modes :
 *   A. En ligne   → formulaire normal, puis récupère et stocke le verifier.
 *   B. Hors-ligne → vérifie PBKDF2 localement via WebCrypto.
 *
 * Sécurité :
 *   - Le verifier est calculé avec un sel PROPRE (offline_salt), distinct
 *     du hash Django. Compromis du verifier → ne compromet PAS le compte.
 *   - 5 tentatives max offline. Au-delà : efface le verifier, exige le réseau.
 *   - Expiration 30 jours : après expiry, l'utilisateur doit se reconnecter en ligne.
 *
 * IndexedDB store : 'sukulu_auth' → clé = username
 *   { username, verifier(hex), offline_salt(b64), iterations, expires_at(ISO), failed_attempts }
 */
(function () {
  'use strict';

  var AUTH_DB    = 'sukulu_auth';
  var AUTH_STORE = 'credentials';
  var MAX_FAILS  = 5;
  var CRED_URL   = '/eco/offline-credential/';

  /* ── IndexedDB auth helpers ── */
  function openAuthDB() {
    return new Promise(function (ok, ko) {
      var r = indexedDB.open(AUTH_DB, 1);
      r.onupgradeneeded = function (e) {
        var db = e.target.result;
        if (!db.objectStoreNames.contains(AUTH_STORE))
          db.createObjectStore(AUTH_STORE, { keyPath: 'username' });
      };
      r.onsuccess = function (e) { ok(e.target.result); };
      r.onerror   = function (e) { ko(e.target.error); };
    });
  }

  function authGet(username) {
    return openAuthDB().then(function (db) {
      return new Promise(function (ok, ko) {
        var r = db.transaction(AUTH_STORE, 'readonly').objectStore(AUTH_STORE).get(username);
        r.onsuccess = function (e) { ok(e.target.result); };
        r.onerror   = function (e) { ko(e.target.error); };
      });
    });
  }

  function authPut(record) {
    return openAuthDB().then(function (db) {
      return new Promise(function (ok, ko) {
        var r = db.transaction(AUTH_STORE, 'readwrite').objectStore(AUTH_STORE).put(record);
        r.onsuccess = function () { ok(); };
        r.onerror   = function (e) { ko(e.target.error); };
      });
    });
  }

  function authDelete(username) {
    return openAuthDB().then(function (db) {
      return new Promise(function (ok, ko) {
        var r = db.transaction(AUTH_STORE, 'readwrite').objectStore(AUTH_STORE).delete(username);
        r.onsuccess = function () { ok(); }; r.onerror = function (e) { ko(e.target.error); };
      });
    });
  }

  /* ── WebCrypto PBKDF2 ── */
  function pbkdf2(password, saltB64, iterations) {
    var enc = new TextEncoder();
    var saltBytes = Uint8Array.from(atob(saltB64), function (c) { return c.charCodeAt(0); });
    return crypto.subtle.importKey(
      'raw', enc.encode(password), 'PBKDF2', false, ['deriveBits']
    ).then(function (key) {
      return crypto.subtle.deriveBits(
        { name: 'PBKDF2', hash: 'SHA-256', salt: saltBytes, iterations: iterations },
        key, 256
      );
    }).then(function (bits) {
      return Array.from(new Uint8Array(bits))
        .map(function (b) { return b.toString(16).padStart(2, '0'); })
        .join('');
    });
  }

  /* ── Stocker le verifier après login en ligne ── */
  function fetchAndStoreCredential() {
    if (!navigator.onLine) return;
    fetch(CRED_URL, {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
    .then(function (r) {
      if (!r.ok) return null;
      return r.json();
    })
    .then(function (d) {
      if (!d || !d.verifier) return;
      return authPut({
        username:        d.username,
        verifier:        d.verifier,
        offline_salt:    d.offline_salt,
        iterations:      d.iterations,
        expires_at:      d.expires_at,
        failed_attempts: 0,
      });
    })
    .catch(function (e) { console.warn('[Sukulu auth]', e); });
  }

  /* ── Vérification offline ── */
  function verifyOffline(username, password) {
    return authGet(username).then(function (stored) {
      if (!stored) return { ok: false, reason: 'no_credential' };

      // Vérifier expiration
      if (new Date(stored.expires_at) < new Date())
        return { ok: false, reason: 'expired' };

      // Limite de tentatives
      if (stored.failed_attempts >= MAX_FAILS)
        return { ok: false, reason: 'locked' };

      // Calcul PBKDF2 local
      return pbkdf2(password, stored.offline_salt, stored.iterations)
        .then(function (computed) {
          if (computed === stored.verifier) {
            // Réinit compteur échecs
            stored.failed_attempts = 0;
            return authPut(stored).then(function () {
              return { ok: true, username: username };
            });
          } else {
            stored.failed_attempts = (stored.failed_attempts || 0) + 1;
            var remaining = MAX_FAILS - stored.failed_attempts;
            return authPut(stored).then(function () {
              if (remaining <= 0) {
                return authDelete(username).then(function () {
                  return { ok: false, reason: 'locked_now' };
                });
              }
              return { ok: false, reason: 'wrong_password', remaining: remaining };
            });
          }
        });
    });
  }

  /* ── Adapter la page de login ── */
  function setupLoginPage() {
    var form = document.querySelector('form[action*="login"]');
    if (!form) return;

    // Après un submit en ligne réussi (redirect), on est redirigé donc
    // on appelle fetchAndStoreCredential dès le chargement d'une page authentifiée.
    // Sur la page login elle-même, si offline, on intercepte.
    if (!navigator.onLine) {
      var submitBtn = form.querySelector('[type=submit]');
      var offlineNote = document.createElement('p');
      offlineNote.style.cssText = 'font-size:.8rem;color:#d97706;margin-top:.5rem;text-align:center;';
      offlineNote.textContent = 'Mode hors-ligne : v\u00e9rification locale.';
      form.appendChild(offlineNote);

      form.addEventListener('submit', function (e) {
        e.preventDefault();
        var username = form.querySelector('[name=username]').value.trim();
        var password = form.querySelector('[name=password]').value;
        if (!username || !password) return;

        if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'V\u00e9rification\u2026'; }

        verifyOffline(username, password).then(function (res) {
          if (res.ok) {
            // Vérif locale OK : on mémorise l'utilisateur et on redirige
            sessionStorage.setItem('sukulu_offline_user', username);
            window.location.href = '/eco/ecoles/';
          } else {
            if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Se connecter'; }
            var msg = {
              no_credential:  'Aucun acc\u00e8s hors-ligne. Connectez-vous une premi\u00e8re fois avec du r\u00e9seau.',
              expired:        'Session hors-ligne expir\u00e9e. Reconnectez-vous en ligne pour la renouveler.',
              locked:         'Trop de tentatives. Reconnectez-vous en ligne pour d\u00e9verrouiller.',
              locked_now:     'Acc\u00e8s hors-ligne bloqu\u00e9 (5 échecs). Reconnectez-vous en ligne.',
              wrong_password: 'Mot de passe incorrect. ' + (res.remaining || 0) + ' tentative(s) restante(s).',
            }[res.reason] || 'Erreur inconnue.';
            var errEl = form.querySelector('.auth-offline-error');
            if (!errEl) {
              errEl = document.createElement('div');
              errEl.className = 'auth-offline-error alert alert-error';
              errEl.style.cssText = 'margin-bottom:.75rem;';
              form.prepend(errEl);
            }
            errEl.textContent = msg;
          }
        }).catch(function () {
          if (submitBtn) { submitBtn.disabled = false; }
        });
      });
    }
  }

  /* ── Init ── */
  document.addEventListener('DOMContentLoaded', function () {
    setupLoginPage();
    // Sur toute page authentifiée (hors login), rafraîchit le verifier en arrière-plan
    if (navigator.onLine && !window.location.pathname.includes('/login')) {
      // Délai pour ne pas bloquer le rendu principal
      setTimeout(fetchAndStoreCredential, 1500);
    }
  });

  window.SukuluAuthOffline = {
    fetchAndStoreCredential: fetchAndStoreCredential,
    verifyOffline:           verifyOffline,
  };
})();
