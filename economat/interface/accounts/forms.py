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
    country = forms.ModelChoiceField(
        label="Pays",
        queryset=None,   # initialisé dans __init__
        widget=forms.Select(attrs={"class": "form-select"}),
        empty_label=None,
    )
    currency = forms.ChoiceField(
        label="Devise",
        choices=[("XOF", "FCFA (XOF) — Afrique de l'Ouest"),
                 ("XAF", "FCFA (XAF) — Afrique Centrale")],
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from economat.infrastructure.models import CountryModel
        self.fields["country"].queryset = CountryModel.objects.filter(is_active=True)


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


class SchoolRegistrationForm(forms.Form):
    """
    Formulaire public d'inscription d'une école.
    Soumis en une seule fois (stepper JS côté client) — validation serveur complète.
    """
    # Étape 1 — École
    school_name = forms.CharField(
        label="Nom de l'école", max_length=200,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Ex : École Primaire Sainte-Marie"}),
    )
    city = forms.CharField(
        label="Ville", max_length=100,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Ex : Dakar"}),
    )
    country_code = forms.ChoiceField(
        label="Pays", choices=[],
        widget=forms.Select(attrs={"class": "form-select", "id": "id_country_code"}),
    )

    # Étape 2 — Encaissement
    payment_methods = forms.MultipleChoiceField(
        label="Moyens d'encaissement acceptés",
        choices=[
            ("ESPECES",      "Espèces"),
            ("MOBILE_MONEY", "Mobile Money"),
            ("VIREMENT",     "Virement bancaire"),
            ("CHEQUE",       "Chèque"),
        ],
        widget=forms.CheckboxSelectMultiple(),
        required=True,
    )
    mobile_operator = forms.CharField(
        label="Opérateur Mobile Money", max_length=60, required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_mobile_operator"}),
    )
    mobile_number = forms.CharField(
        label="Numéro Mobile Money", max_length=30, required=False,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Ex : 771234567"}),
    )

    # Étape 3 — Gérant
    manager_first_name = forms.CharField(
        label="Prénom", max_length=100,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Kofi"}),
    )
    manager_last_name = forms.CharField(
        label="Nom", max_length=100,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "MENSAH"}),
    )
    manager_email = forms.EmailField(
        label="Adresse email",
        widget=forms.EmailInput(attrs={"class": "form-input", "placeholder": "kofi.mensah@ecole.sn"}),
    )
    manager_phone = forms.CharField(
        label="Téléphone (optionnel)", max_length=30, required=False,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Ex : +221 77 123 45 67"}),
    )

    # Champ caché — UUID idempotence généré côté JS
    client_uuid = forms.UUIDField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from economat.infrastructure.models import CountryModel
        countries = CountryModel.objects.filter(is_active=True).values_list("code", "name")
        self.fields["country_code"].choices = [("", "Sélectionnez un pays…")] + list(countries)



class ProfileForm(forms.Form):
    """Formulaire de modification du profil utilisateur."""
    first_name = forms.CharField(
        label="Prénom", max_length=100,
        widget=forms.TextInput(attrs={"class": "form-input"}),
    )
    last_name = forms.CharField(
        label="Nom", max_length=100,
        widget=forms.TextInput(attrs={"class": "form-input"}),
    )
    email = forms.EmailField(
        label="Adresse email", required=False,
        widget=forms.EmailInput(attrs={"class": "form-input",
                                       "placeholder": "ex: contact@ecole.sn"}),
    )


class ChangePasswordForm(forms.Form):
    """Formulaire de changement de mot de passe."""
    old_password = forms.CharField(
        label="Mot de passe actuel",
        widget=forms.PasswordInput(attrs={"class": "form-input",
                                          "autocomplete": "current-password"}),
    )
    new_password1 = forms.CharField(
        label="Nouveau mot de passe", min_length=8,
        widget=forms.PasswordInput(attrs={"class": "form-input",
                                          "autocomplete": "new-password"}),
        help_text="8 caractères minimum.",
    )
    new_password2 = forms.CharField(
        label="Confirmer le nouveau mot de passe",
        widget=forms.PasswordInput(attrs={"class": "form-input",
                                          "autocomplete": "new-password"}),
    )

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("new_password1")
        p2 = cleaned.get("new_password2")
        if p1 and p2 and p1 != p2:
            self.add_error("new_password2",
                           "Les deux mots de passe ne correspondent pas.")
        return cleaned
