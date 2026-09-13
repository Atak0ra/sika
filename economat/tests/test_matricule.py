"""
tests/test_matricule.py
==========================
Tests du générateur de matricule sécurisé (suffixe aléatoire, pas de
date/heure devinable).
"""
import re

from economat.domain.student.matricule import generate_matricule

MATRICULE_RE = re.compile(r"^[A-Z]{6}-[A-Z0-9]{7}$")
SAFE_ALPHABET = set("23456789ABCDEFGHJKMNPQRSTUVWXYZ")


def test_format_matches_prefix_and_random_suffix():
    mat = generate_matricule("Diallo", "Awa")
    assert MATRICULE_RE.match(mat), f"format inattendu : {mat}"
    assert mat.startswith("DIAAWA-")


def test_suffix_uses_unambiguous_alphabet_only():
    mat = generate_matricule("Kone", "Ba")
    suffix = mat.split("-")[1]
    assert set(suffix) <= SAFE_ALPHABET, f"caractère ambigu dans {suffix}"


def test_suffix_excludes_confusable_characters():
    # 0/O, 1/I/L ne doivent jamais apparaître dans le suffixe
    for _ in range(50):
        mat = generate_matricule("Traore", "Fatou")
        suffix = mat.split("-")[1]
        assert not any(c in suffix for c in "01IOL")


def test_two_generations_for_same_student_differ():
    # Avant : deux inscriptions à la même seconde produisaient le même
    # matricule (collision). Maintenant : le suffixe aléatoire les distingue
    # même sans écart de temps.
    mat1 = generate_matricule("Ben Ali", "Aicha")
    mat2 = generate_matricule("Ben Ali", "Aicha")
    assert mat1 != mat2


def test_enrolled_at_parameter_still_accepted_but_ignored():
    import datetime
    # Ne doit pas lever — compat avec les appelants existants qui passent
    # encore une date (register_student.py).
    mat = generate_matricule("Sall", "Fatou", datetime.datetime(2026, 9, 11, 14, 30, 52))
    assert MATRICULE_RE.match(mat)


def test_no_date_or_time_pattern_leaks_in_output():
    # Le suffixe ne doit jamais ressembler à AAMMJJ ou HHMMSS (régression :
    # l'ancien format encodait la date/heure d'inscription, devinable).
    mat = generate_matricule("Diop", "Moussa")
    suffix = mat.split("-")[1]
    assert not suffix.isdigit()  # un suffixe 100% numérique ressemblerait à une date
