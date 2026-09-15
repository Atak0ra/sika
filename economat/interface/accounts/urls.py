"""
interface/accounts/urls.py
"""
from django.urls import path
from . import views
from .landing import landing

urlpatterns = [
    path("",                  landing,                       name="landing"),
    path("login/",            views.login_view,              name="login"),
    path("logout/",           views.logout_view,             name="logout"),
    path("ecoles/",           views.school_selector,         name="school_selector"),
    path("inscription/",      views.register_school,         name="register_school"),
    path("autres-pays/",      views.other_countries,         name="other_countries"),
    path("<str:school_id>/equipe/",
         views.team,                                          name="team"),
    path("<str:school_id>/equipe/<str:member_id>/toggle/",
         views.toggle_collaborator,                           name="toggle_collaborator"),
    path("mon-compte/",              views.profile,          name="profile"),
    path("mon-compte/mot-de-passe/", views.change_password,  name="change_password"),
    path("offline-credential/",      views.offline_credential, name="offline_credential"),
]

