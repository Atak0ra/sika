"""
config/settings_test.py
=========================
Surcharge minimaliste pour les tests : force SQLite en mémoire
afin d'éviter la dépendance à la base Neon (PostgreSQL cloud).
"""
from config.settings import *  # noqa: F401, F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Désactive le cache en test
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# Pas de logs HTTP parasites en test
LOGGING = {}
