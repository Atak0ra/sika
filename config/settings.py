import os
from pathlib import Path
from dotenv import load_dotenv

# ── Chemins ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# Charge .env si présent (priorité aux variables déjà définies dans l'OS/Vercel)
load_dotenv(BASE_DIR / ".env", override=False)

# ── Sécurité ──────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-key-change-me-in-production!!",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "True").strip().lower() in ("true", "1", "yes")

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

# Vercel place l'app derrière un proxy HTTPS : sans ça, Django voit une requête
# HTTP côté interne et rejette le POST CSRF (mismatch de scheme).
CSRF_TRUSTED_ORIGINS = [
    f"https://{h}" for h in ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1")
]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ── Applications ──────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Sukulu — architecture hexagonale / DDD
    "economat",
]

# ── Middleware ────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise : sert les fichiers statiques directement depuis Django/Gunicorn.
    # Positionné juste après SecurityMiddleware (avant tout le reste) pour
    # court-circuiter les requêtes /static/ sans passer par les vues Django.
    # Requis en prod (Vercel) pour que le Service Worker puisse mettre en cache
    # les assets JS/CSS offline de manière fiable.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ── Base de données ───────────────────────────────────────────────────────────
# Local / dev : SQLite (fichier écrit sur disque, OK en dehors de Vercel).
# Prod (Vercel) : filesystem en lecture seule (sauf /tmp, éphémère) → SQLite ne
# fonctionne pas ("unable to open database file"). Dès que DATABASE_URL est
# défini (Postgres — Vercel Postgres/Neon/Supabase…), on l'utilise à la place.
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if DATABASE_URL:
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=0,       # pas de connexions persistantes en serverless
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {
                # Améliore les performances pour les grosses requêtes
                "timeout": 30,
            },
        }
    }

# ── Validation des mots de passe ──────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── Internationalisation ──────────────────────────────────────────────────────
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

# ── Fichiers statiques ────────────────────────────────────────────────────────
STATIC_URL  = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# WhiteNoise : compression gzip/brotli + headers Cache-Control immuables
# pour les assets versionnés. Améliore les scores Lighthouse et le cache SW.
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Uploads et fichiers temporaires (SQLite externes, CSV convertis)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ── Clé primaire par défaut ───────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Taille max des uploads (50 MB)
DATA_UPLOAD_MAX_MEMORY_SIZE = 52_428_800
FILE_UPLOAD_MAX_MEMORY_SIZE = 52_428_800

# ── Sécurité HTTPS (prod Vercel — uniquement si DEBUG=False) ─────────────────
if not DEBUG:
    SECURE_SSL_REDIRECT          = True
    SECURE_HSTS_SECONDS          = 31_536_000   # 1 an
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD          = True
    SESSION_COOKIE_SECURE        = True
    CSRF_COOKIE_SECURE           = True

# ── Authentification / Sukulu ──────────────────────────────────────────────
LOGIN_URL           = "/eco/login/"
LOGIN_REDIRECT_URL  = "/eco/ecoles/"
LOGOUT_REDIRECT_URL = "/eco/"
