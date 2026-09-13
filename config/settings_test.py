"""
config/settings_test.py
=========================
Surcharge minimaliste pour les tests : force SQLite en mémoire
afin d'éviter la dépendance à la base Neon (PostgreSQL cloud).
"""
from config.settings import *  # noqa: F401, F403

# Le client de test Django envoie Host: testserver par défaut — nécessaire
# pour toute vue qui appelle request.get_host()/build_absolute_uri()
# (ex. construction du notify_url du portail de paiement parent).
ALLOWED_HOSTS = [*ALLOWED_HOSTS, "testserver"]

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
