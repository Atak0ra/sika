from django.urls import path
from . import views

urlpatterns = [
    path("",                                                views.dashboard,            name="director_dashboard"),

    # Années scolaires
    path("<str:school_id>/annees/",                         views.manage_years,         name="manage_years"),
    path("<str:school_id>/annees/<str:year_id>/activer/",   views.activate_year,        name="activate_year"),
    path("<str:school_id>/annees/<str:year_id>/cloturer/",  views.close_year,           name="close_year"),

    # Structure : niveaux + classes (DIRECTOR + SECRETARY)
    path("<str:school_id>/<str:year_id>/niveaux/",
         views.add_level,          name="add_level"),
    path("<str:school_id>/<str:year_id>/niveaux/<str:level_id>/classes/",
         views.add_class,          name="add_class"),

    # Tarifs (DIRECTOR)
    path("<str:school_id>/<str:year_id>/tarifs/",
         views.configure_pricing,  name="configure_pricing"),

    # Vue dédiée par classe
    path("<str:school_id>/<str:year_id>/classes/<str:class_id>/",
         views.class_detail,       name="class_detail"),

    # Élèves
    path("<str:school_id>/<str:year_id>/eleves/",
         views.students_list,      name="students_list"),
    path("<str:school_id>/<str:year_id>/eleves/nouveau/",
         views.register_student,   name="register_student"),
    path("<str:school_id>/<str:year_id>/eleves/promotion/",
         views.promote_class,      name="promote_class"),
    path("<str:school_id>/<str:year_id>/eleves/<str:enrollment_id>/",
         views.student_detail,     name="student_detail"),

    # Chat IA (DIRECTOR)
    path("<str:school_id>/<str:year_id>/chat/",
         views.chat,               name="director_chat"),

    # Alertes de paiement (DIRECTOR)
    path("<str:school_id>/<str:year_id>/alertes/",
         views.alerts,             name="alerts"),

    # Export CSV
    path("<str:school_id>/<str:year_id>/export/renvoyables/",
         views.export_renvoyables, name="export_renvoyables"),

    # Paramètres école
    path("<str:school_id>/parametres/",
         views.school_settings,    name="school_settings"),
]
