"""
economat/apps.py — Configuration de l'app Django économat.
"""
from django.apps import AppConfig


class EconomatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name               = "economat"
    verbose_name       = "Sukulu"
