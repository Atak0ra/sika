"""
interface/parent_portal/forms.py
===================================
Formulaire de recherche élève par école + matricule.

Sécurité : le matricule est normalisé (majuscules, espaces retirés) mais
JAMAIS recherché en `icontains` — un match partiel ne doit jamais être
possible (voir InitiateOnlinePaymentUseCase / la vue search qui applique
le même principe pour la recherche seule).
"""
import re

from django import forms

from economat.domain.payment.value_objects import mobile_operator_style, mobile_operators_for_country
from economat.infrastructure.models import SchoolModel


class SchoolMatriculeForm(forms.Form):
    school = forms.ModelChoiceField(
        label="École", queryset=SchoolModel.objects.order_by("name"),
        empty_label="Sélectionnez l'école",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    matricule = forms.CharField(
        label="Matricule de l'élève", max_length=30,
        widget=forms.TextInput(attrs={
            "class": "form-input", "placeholder": "Ex : DIAAWA-7K9XQPR",
            "autocomplete": "off", "autocapitalize": "characters",
        }),
    )

    def clean_matricule(self) -> str:
        return self.cleaned_data["matricule"].strip().upper()


class OnlinePaymentForm(forms.Form):
    amount_fcfa = forms.IntegerField(
        label="Montant à payer (FCFA)", min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-input", "placeholder": "Ex : 25000"}),
    )
    mobile_operator = forms.ChoiceField(label="Opérateur Mobile Money", choices=[])
    mobile_number = forms.CharField(
        label="Votre numéro Mobile Money", max_length=20,
        widget=forms.TextInput(attrs={"class": "form-input", "inputmode": "tel",
                                       "placeholder": "Ex : 07 00 00 00 00"}),
    )

    def __init__(self, *args, country: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        operators = mobile_operators_for_country(country)
        self.fields["mobile_operator"].choices = [(op, op) for op in operators]
        self.mobile_operator_options = [
            {"value": op, "style": mobile_operator_style(op)} for op in operators
        ]

    def clean_mobile_number(self) -> str:
        number = self.cleaned_data["mobile_number"]
        digits = re.sub(r"\D", "", number)
        if len(digits) < 8:
            raise forms.ValidationError("Numéro trop court.")
        return number
