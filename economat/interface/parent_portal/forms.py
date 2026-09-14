"""
interface/parent_portal/forms.py
===================================
Formulaire de recherche élève par pays + école + matricule.

Sécurité : le matricule est normalisé (majuscules, espaces retirés) mais
JAMAIS recherché en `icontains` — un match partiel ne doit jamais être
possible.

Désambiguïsation : le champ Pays est placé en premier et filtre les écoles
côté JS. Ainsi, deux écoles homonymes dans deux pays différents ne peuvent
jamais entrer en collision. La vue `search` pré-sélectionne le pays selon
l'IP du parent (header Vercel/Cloudflare), avec fallback Sénégal.

Cohérence : clean() vérifie que l'école soumise appartient bien au pays
choisi — sans jamais révéler si l'école existe ou non dans un autre pays
(même message générique que pour le matricule introuvable).
"""
import re

from django import forms

from economat.domain.payment.value_objects import mobile_operator_style, mobile_operators_for_country
from economat.infrastructure.models import CountryModel, SchoolModel


class SchoolMatriculeForm(forms.Form):
    country = forms.ModelChoiceField(
        label="Pays",
        queryset=CountryModel.objects.filter(is_active=True).order_by("name"),
        empty_label=None,
        widget=forms.Select(attrs={"class": "form-select", "id": "countrySelect"}),
    )
    school = forms.ModelChoiceField(
        label="École",
        # Le queryset est volontairement large (toutes les écoles) : la
        # validation de cohérence pays↔école est faite dans clean().
        # Côté JS, la liste est filtrée par pays avant tout envoi.
        queryset=SchoolModel.objects.select_related("country").order_by("name"),
        empty_label="Sélectionnez l'école",
        widget=forms.Select(attrs={"class": "form-select", "style": "display:none"}),
    )
    matricule = forms.CharField(
        label="Matricule de l'élève", max_length=30,
        widget=forms.TextInput(attrs={
            "class": "form-input", "placeholder": "Ex : DIAAWA-7K9XQPR",
            "autocomplete": "off", "autocapitalize": "characters",
        }),
    )

    def __init__(self, *args, initial_country: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if initial_country and not self.data:
            # Pré-sélectionner le pays détecté par IP (uniquement sur GET,
            # pas quand le formulaire a été soumis — self.data serait rempli)
            try:
                country_obj = CountryModel.objects.get(
                    code=initial_country, is_active=True
                )
                self.initial["country"] = country_obj.pk
            except CountryModel.DoesNotExist:
                pass

    def clean_matricule(self) -> str:
        return self.cleaned_data["matricule"].strip().upper()

    def clean(self):
        cleaned = super().clean()
        country = cleaned.get("country")
        school = cleaned.get("school")

        if country and school:
            # Vérifier que l'école appartient bien au pays choisi.
            # Message générique : ne révèle pas si l'école existe dans un
            # autre pays (même principe de sécurité que pour le matricule).
            if school.country_id != country.pk:
                self.add_error(
                    None,
                    "École ou matricule introuvable. Vérifiez votre saisie.",
                )
        return cleaned


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

    def __init__(self, *args, country=None, **kwargs):
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

