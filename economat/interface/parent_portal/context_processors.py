"""
interface/parent_portal/context_processors.py
================================================
Injecte l'élève actif du portail parent (barre de contexte persistante du
shell `_base_parent.html`) sans que chaque vue ait à s'en soucier.

Scope : uniquement les requêtes sous /payer/ (le portail parent). Ailleurs
dans l'appli (staff), la variable reste absente — le shell staff ne la lit
de toute façon jamais.
"""
from __future__ import annotations


def parent_portal_active_student(request):
    if "/payer/" not in request.path:
        return {}

    # Masquée sur la page de recherche elle-même : le parent y choisit
    # justement un élève, la barre "vous consultez / changer d'élève"
    # n'a pas de sens tant qu'aucune recherche n'a abouti sur cette visite.
    if getattr(request, "resolver_match", None) and request.resolver_match.url_name == "parent_portal_search":
        return {}

    student_id = request.session.get("parent_portal_student_id")
    if not student_id:
        return {}

    from economat.infrastructure.models import StudentModel
    student = StudentModel.objects.filter(pk=student_id).first()
    if student is None:
        return {}

    return {"parent_portal_active_student": student}
