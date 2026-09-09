"""
interface/econome/urls.py — Routes de l'économe.
"""
from django.urls import path
from . import views

urlpatterns = [
    path("",                  views.dashboard,          name="econome_dashboard"),
    path("encaisser/",        views.record_payment,     name="record_payment"),
    path("api/eleves/",       views.student_search_api, name="student_search_api"),
]
