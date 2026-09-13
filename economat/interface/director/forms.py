from django import forms

PAYMENT_MODE_CHOICES = [
    ("TRANCHES", "3 tranches (40% + 30% + 30%)"),
    ("MENSUEL",  "Mensualités (10 mois)"),
    ("UNIQUE",   "Paiement unique à l'inscription"),
]


class CreateSchoolYearForm(forms.Form):
    label = forms.CharField(
        label="Label", max_length=20,
        widget=forms.TextInput(attrs={"class":"form-input", "placeholder":"ex. 2025-2026"}),
        help_text="Format recommandé : AAAA-AAAA",
    )
    start_date = forms.DateField(
        label="Date de début",
        widget=forms.DateInput(attrs={"type":"date","class":"form-input"}),
    )
    end_date = forms.DateField(
        label="Date de fin",
        widget=forms.DateInput(attrs={"type":"date","class":"form-input"}),
    )
    def clean(self):
        d = super().clean()
        if d.get("end_date") and d.get("start_date") and d["end_date"] <= d["start_date"]:
            self.add_error("end_date", "La date de fin doit être après la date de début.")
        return d


class CloseYearForm(forms.Form):
    confirm = forms.BooleanField(
        label="Je confirme la clôture irréversible de cette année scolaire",
        required=True,
    )


class AddLevelForm(forms.Form):
    level_name = forms.CharField(
        label="Nom du niveau", max_length=100,
        widget=forms.TextInput(attrs={"class":"form-input","placeholder":"Ex : CM1, CM2, 6ème…"}),
        help_text="Ce nom doit être unique dans l'année.",
    )
    annual_fee_fcfa = forms.IntegerField(
        label="Frais annuels (FCFA)", min_value=0, initial=0,
        widget=forms.NumberInput(attrs={"class":"form-input","placeholder":"Ex : 150000"}),
        help_text="Vous pouvez laisser 0 et configurer les tarifs plus tard.",
    )
    payment_mode = forms.ChoiceField(
        label="Mode de paiement", choices=PAYMENT_MODE_CHOICES,
        widget=forms.RadioSelect(), initial="TRANCHES",
    )


class AddClassForm(forms.Form):
    class_name = forms.CharField(
        label="Nom de la classe", max_length=100,
        widget=forms.TextInput(attrs={"class":"form-input","placeholder":"Ex : CM2 A, 6ème B…"}),
    )
    capacity = forms.IntegerField(
        label="Capacité", min_value=1, initial=40,
        widget=forms.NumberInput(attrs={"class":"form-input"}),
    )


class ConfigurePricingForm(forms.Form):
    level_id        = forms.CharField(widget=forms.HiddenInput())
    annual_fee_fcfa = forms.IntegerField(
        label="Frais annuels (FCFA)", min_value=1,
        widget=forms.NumberInput(attrs={"class":"form-input","placeholder":"Ex : 150000"}),
    )
    payment_mode = forms.ChoiceField(
        label="Mode de paiement", choices=PAYMENT_MODE_CHOICES,
        widget=forms.RadioSelect(), initial="TRANCHES",
    )


class RegisterStudentForm(forms.Form):
    first_name = forms.CharField(label="Prénom", max_length=100,
                                  widget=forms.TextInput(attrs={"class":"form-input"}))
    last_name  = forms.CharField(label="Nom de famille", max_length=100,
                                  widget=forms.TextInput(attrs={"class":"form-input"}))
    school_id  = forms.CharField(widget=forms.HiddenInput())
    year_id    = forms.CharField(widget=forms.HiddenInput())
    level_id   = forms.ChoiceField(label="Niveau",
                                    widget=forms.Select(attrs={"class":"form-select"}))
    class_id   = forms.ChoiceField(label="Classe",
                                    widget=forms.Select(attrs={"class":"form-select"}))
    date_of_birth   = forms.DateField(label="Date de naissance", required=False,
                                       widget=forms.DateInput(attrs={"type":"date","class":"form-input"}))
    enrollment_date = forms.DateField(label="Date d'inscription", required=False,
                                       widget=forms.DateInput(attrs={"type":"date","class":"form-input"}))
    notes = forms.CharField(label="Observations", required=False, max_length=500,
                             widget=forms.Textarea(attrs={"rows":2,"class":"form-textarea"}))
    # ── Contact parent / tuteur ──────────────────────────────────────────
    parent_name = forms.CharField(
        label="Nom du parent / tuteur", required=False, max_length=200,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Ex : Koffi AMEGAN"}),
    )
    parent_phone = forms.CharField(
        label="Téléphone", required=False, max_length=30,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Ex : +228 90 00 00 00",
                                      "type": "tel"}),
    )
    parent_relation = forms.ChoiceField(
        label="Lien de parenté", required=False,
        choices=[("", "— Choisir —"), ("PERE", "Père"), ("MERE", "Mère"),
                 ("TUTEUR", "Tuteur / Tutrice"), ("AUTRE", "Autre")],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    # ────────────────────────────────────────────────────────────────────

    def __init__(self, *args, year_orm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if year_orm:
            from economat.infrastructure.models import LevelModel, ClassModel
            levels = LevelModel.objects.filter(school_year_id=year_orm.id).order_by("name")
            self.fields["level_id"].choices = [(str(l.id), l.name) for l in levels]
            classes = ClassModel.objects.filter(
                level__school_year_id=year_orm.id
            ).select_related("level").order_by("level__name","name")
            self.fields["class_id"].choices = [(str(c.id), f"{c.level.name} — {c.name}") for c in classes]


class DirectorChatForm(forms.Form):
    question = forms.CharField(
        label="Votre question", max_length=500,
        widget=forms.TextInput(attrs={
            "placeholder":"Ex : Combien d'élèves en retard en CM2 ?",
            "autocomplete":"off", "class":"chat-input", "id":"directorChatInput",
        }),
    )


SCHOOL_COUNTRY_CHOICES = [
    ("Sénégal",        "Sénégal"),
    ("Côte d'Ivoire",  "Côte d'Ivoire"),
    ("Togo",           "Togo"),
    ("Bénin",          "Bénin"),
    ("Guinée Conakry", "Guinée Conakry"),
]


class SchoolSettingsForm(forms.Form):
    tolerance_days = forms.IntegerField(
        label="Seuil de tolérance (jours avant alerte prioritaire)",
        min_value=1, max_value=365,
        widget=forms.NumberInput(attrs={"class":"form-input","placeholder":"30"}),
        help_text="Nombre de jours de retard au-delà duquel un élève passe en alerte prioritaire.",
    )
    country = forms.ChoiceField(
        label="Pays",
        choices=SCHOOL_COUNTRY_CHOICES,
        widget=forms.Select(attrs={"class":"form-select"}),
        help_text="Détermine les opérateurs Mobile Money proposés à l'encaissement.",
    )
