"""
interface/accounts/forms.py
==============================
Formulaires du module Accounts (authentification + onboarding + équipe).
"""

from django import forms


class SignUpForm(forms.Form):
    """Formulaire d'inscription directeur (étape 1)."""
    first_name = forms.CharField(
        label="Prénom", max_length=100,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Mamadou"}),
    )
    last_name = forms.CharField(
        label="Nom", max_length=100,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "DIALLO"}),
    )
    username = forms.CharField(
        label="Identifiant de connexion", max_length=150,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "m.diallo",
                                      "autocomplete": "username"}),
        help_text="Lettres, chiffres et . _ - uniquement. Servira à vous connecter.",
    )
    password = forms.CharField(
        label="Mot de passe", min_length=6,
        widget=forms.PasswordInput(attrs={"class": "form-input", "autocomplete": "new-password"}),
    )
    password_confirm = forms.CharField(
        label="Confirmer le mot de passe",
        widget=forms.PasswordInput(attrs={"class": "form-input", "autocomplete": "new-password"}),
    )
    email = forms.EmailField(
        label="Email (optionnel)", required=False,
        widget=forms.EmailInput(attrs={"class": "form-input", "placeholder": "m.diallo@ecole.sn"}),
    )

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password"), cleaned.get("password_confirm")
        if p1 and p2 and p1 != p2:
            self.add_error("password_confirm", "Les deux mots de passe ne correspondent pas.")
        return cleaned


class LoginForm(forms.Form):
    """Formulaire de connexion."""
    username = forms.CharField(
        label="Identifiant",
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Votre identifiant",
                                      "autocomplete": "username", "autofocus": True}),
    )
    password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={"class": "form-input", "autocomplete": "current-password"}),
    )


class CreateSchoolForm(forms.Form):
    """Formulaire de création de l'école (étape 2 — onboarding directeur)."""
    school_name = forms.CharField(
        label="Nom de l'école", max_length=200,
        widget=forms.TextInput(attrs={"class": "form-input",
                                      "placeholder": "Ex : École Primaire Sainte-Marie"}),
    )
    city = forms.CharField(
        label="Ville", max_length=100,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Ex : Dakar"}),
    )
    country = forms.CharField(
        label="Pays", max_length=100, initial="Sénégal",
        widget=forms.TextInput(attrs={"class": "form-input"}),
    )
    currency = forms.ChoiceField(
        label="Devise",
        choices=[("XOF", "FCFA (XOF) — Afrique de l'Ouest"),
                 ("XAF", "FCFA (XAF) — Afrique Centrale")],
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class CreateCollaboratorForm(forms.Form):
    """Formulaire de création directe d'un collaborateur (secrétaire / économe)."""
    ROLE_CHOICES = [
        ("ECONOME",   "Économe — saisie des paiements"),
        ("SECRETARY", "Secrétaire — inscriptions élèves + lecture"),
    ]
    first_name = forms.CharField(
        label="Prénom", max_length=100,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Aïssatou"}),
    )
    last_name = forms.CharField(
        label="Nom", max_length=100,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "SOW"}),
    )
    username = forms.CharField(
        label="Identifiant de connexion", max_length=150,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "a.sow"}),
        help_text="Ce sera son identifiant pour se connecter.",
    )
    password = forms.CharField(
        label="Mot de passe provisoire", min_length=6,
        widget=forms.PasswordInput(attrs={"class": "form-input"}),
        help_text="Communiquez-lui ce mot de passe. Il pourra le changer ensuite.",
    )
    role = forms.ChoiceField(
        label="Rôle", choices=ROLE_CHOICES,
        widget=forms.RadioSelect(attrs={"class": "radio-group"}),
    )
