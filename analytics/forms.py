from django import forms


class QueryForm(forms.Form):
    """Formulaire de question en langage naturel avec choix du format de sortie."""

    OUTPUT_FORMATS = [
        ("kpi",       "KPI"),
        ("chart",     "Graphique"),
        ("dashboard", "Dashboard"),
    ]

    question = forms.CharField(
        label="Question",
        max_length=500,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Posez une question sur vos transactions…",
                "autocomplete": "off",
                "id": "questionInput",
            }
        ),
        help_text="Posez votre question en français ou en anglais.",
    )

    output_format = forms.ChoiceField(
        label="Format",
        choices=OUTPUT_FORMATS,
        initial="kpi",
        widget=forms.RadioSelect(),
    )

