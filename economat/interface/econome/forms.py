from django import forms
from django.utils import timezone

PAYMENT_METHOD_CHOICES = [
    ("ESPECES",      "💵 Espèces"),
    ("MOBILE_MONEY", "📱 Mobile Money (Orange Money, Wave…)"),
    ("VIREMENT",     "🏦 Virement bancaire"),
    ("CHEQUE",       "📝 Chèque"),
]


class RecordPaymentForm(forms.Form):
    student_id = forms.CharField(
        label="Identifiant élève", max_length=36,
        widget=forms.TextInput(attrs={"placeholder":"UUID de l'élève",
                                       "autocomplete":"off","class":"form-input"}),
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
    notes = forms.CharField(
        label="Observations", required=False, max_length=500,
        widget=forms.Textarea(attrs={"rows":2,"placeholder":"Remarque optionnelle…",
                                      "class":"form-textarea"}),
    )


class StudentSearchForm(forms.Form):
    query = forms.CharField(
        label="Rechercher un élève", max_length=100,
        widget=forms.TextInput(attrs={"placeholder":"Nom ou prénom…","autocomplete":"off",
                                       "class":"form-input","id":"studentSearchInput"}),
    )
