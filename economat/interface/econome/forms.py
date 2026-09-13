import re

from django import forms
from django.utils import timezone

from economat.domain.payment.value_objects import (
    mobile_operator_style,
    mobile_operators_for_country,
)

PAYMENT_METHOD_CHOICES = [
    ("ESPECES",      "Espèces"),
    ("MOBILE_MONEY", "Mobile Money"),
    ("VIREMENT",     "Virement bancaire"),
    ("CHEQUE",       "Chèque"),
]


class RecordPaymentForm(forms.Form):
    student_id = forms.CharField(
        label="Identifiant élève", max_length=36,
        widget=forms.HiddenInput(),
    )
    amount_fcfa = forms.IntegerField(
        label="Montant (FCFA)", min_value=1,
        widget=forms.NumberInput(attrs={"placeholder":"Ex : 25000","class":"form-input"}),
    )
    payment_date = forms.DateField(
        label="Date de paiement",
        widget=forms.DateInput(attrs={"type":"date","class":"form-input"}),
        initial=timezone.now().date,
    )
    method = forms.ChoiceField(
        label="Moyen de paiement", choices=PAYMENT_METHOD_CHOICES,
        initial="ESPECES", widget=forms.Select(attrs={"class":"form-select"}),
    )
    # Choices peuplées dynamiquement dans __init__ selon le pays de l'école —
    # requis seulement si method == MOBILE_MONEY (voir clean()). Rendu en
    # cartes (voir mobile_operator_options) plutôt qu'en <select>.
    mobile_operator = forms.ChoiceField(
        label="Opérateur Mobile Money", required=False, choices=[],
        widget=forms.RadioSelect,
    )
    # Requis seulement si method == MOBILE_MONEY (voir clean()).
    mobile_number = forms.CharField(
        label="Numéro Mobile Money", required=False, max_length=20,
        widget=forms.TextInput(attrs={"class":"form-input","placeholder":"Ex : 07 00 00 00 00",
                                       "inputmode":"tel"}),
    )
    notes = forms.CharField(
        label="Observations", required=False, max_length=500,
        widget=forms.Textarea(attrs={"rows":2,"placeholder":"Remarque optionnelle…",
                                      "class":"form-textarea"}),
    )
    paid_by = forms.CharField(
        label="Payé par (optionnel)", required=False, max_length=200,
        widget=forms.TextInput(attrs={"class": "form-input",
                                      "placeholder": "Nom de la personne venue payer…"}),
    )

    def __init__(self, *args, country: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        operators = mobile_operators_for_country(country)
        self.fields["mobile_operator"].choices = [(op, op) for op in operators]
        # Options enrichies (monogramme + couleurs) pour un rendu en cartes
        # dans le template, homogène avec les cartes "Moyen de paiement".
        self.mobile_operator_options = [
            {"value": op, "style": mobile_operator_style(op)} for op in operators
        ]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("method") == "MOBILE_MONEY":
            if not cleaned.get("mobile_operator"):
                self.add_error("mobile_operator", "Choisissez l'opérateur Mobile Money utilisé.")
            number = cleaned.get("mobile_number", "")
            digits = re.sub(r"\D", "", number)
            if not number:
                self.add_error("mobile_number", "Renseignez le numéro utilisé pour le paiement.")
            elif len(digits) < 8:
                self.add_error("mobile_number", "Numéro trop court.")
        return cleaned


class StudentSearchForm(forms.Form):
    query = forms.CharField(
        label="Rechercher un élève", max_length=100,
        widget=forms.TextInput(attrs={"placeholder":"Nom ou prénom…","autocomplete":"off",
                                       "class":"form-input","id":"studentSearchInput"}),
    )
