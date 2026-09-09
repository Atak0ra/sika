from django.urls import path
from . import views

app_name = "analytics"

urlpatterns = [
    path("",                          views.index,              name="index"),
    path("source/new/",               views.source_setup,       name="source_setup"),
    path("source/test/",              views.source_test,        name="source_test"),
    path("source/confirm/",           views.source_confirm,     name="source_confirm"),
]
