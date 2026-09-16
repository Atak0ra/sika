"""
infrastructure/models.py
==========================
Modèles ORM — NOUVEAU SCHEMA avec année scolaire comme racine temporelle.

Hiérarchie des tables :
  economat_country               (référentiel pays — géré via l'admin)
  economat_school
    └── economat_school_year       ("2024-2025", ACTIVE/CLOSED)
          ├── economat_level           (rattaché à l'année)
          │     └── economat_class
          └── via enrollment
  economat_student               (identité permanente)
    └── economat_enrollment         (année + classe + élève)
          └── economat_payment
  economat_membership            (inchangé)
"""
import uuid

from django.db import models


class CountryModel(models.Model):
    """
    Référentiel des pays supportés. Géré via l'admin Django : ajouter un
    pays (Congo, Guinée Bissau…) = créer une entrée ici, sans toucher au code.

    Champs clés :
      code             — code ISO 3166-1 alpha-2 (ex. "SN", "GN"), clé métier
      name             — libellé affiché (ex. "Sénégal", "Guinée Conakry")
      currency         — devise par défaut (XOF, XAF…)
      payment_provider — passerelle Mobile Money active pour ce pays
                         ("samirpay", "crpay", ou "" = aucune / Fake)
      mobile_operators — liste JSON des opérateurs Mobile Money
                         ex. ["Orange Money", "Wave"]
      dial_code        — indicatif téléphonique international (ex. "+221")
      is_active        — faux = pays masqué dans les formulaires (pas supprimé)
    """
    PROVIDER_CHOICES = [
        ("",          "Aucune (mode test / Fake)"),
        ("samirpay",  "Samirpay (Sénégal)"),
        ("crpay",     "CRPay (Guinée Conakry)"),
    ]

    code             = models.CharField(max_length=2, unique=True, db_index=True,
                                        verbose_name="Code ISO", help_text="Code ISO 3166-1 alpha-2 (ex. SN)")
    name             = models.CharField(max_length=100, verbose_name="Pays")
    currency         = models.CharField(max_length=10, default="XOF",
                                        verbose_name="Devise", help_text="XOF, XAF…")
    payment_provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES,
                                        blank=True, default="",
                                        verbose_name="Passerelle de paiement")
    mobile_operators = models.JSONField(default=list, blank=True,
                                        verbose_name="Opérateurs Mobile Money",
                                        help_text='Liste JSON, ex. ["Orange Money", "Wave"]')
    dial_code        = models.CharField(max_length=6, blank=True, default="",
                                        verbose_name="Indicatif téléphonique",
                                        help_text='Ex. "+221"')
    is_active        = models.BooleanField(default=True, verbose_name="Actif",
                                           help_text="Masqué dans les formulaires si décoché")

    class Meta:
        app_label  = "economat"
        db_table   = "economat_country"
        ordering   = ["name"]
        verbose_name        = "Pays"
        verbose_name_plural = "Pays"

    def __str__(self):
        return f"{self.name} ({self.code})"


class SchoolModel(models.Model):
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name           = models.CharField(max_length=200)
    city           = models.CharField(max_length=100)
    country        = models.ForeignKey(
        CountryModel,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="schools",
        verbose_name="Pays",
    )
    currency       = models.CharField(max_length=10, default="XOF")
    tolerance_days = models.PositiveSmallIntegerField(default=30)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        app_label  = "economat"
        db_table   = "economat_school"
        ordering   = ["name"]

    def __str__(self): return f"{self.name} ({self.city})"


class SchoolYearModel(models.Model):
    """Année scolaire — racine temporelle de toute la configuration."""
    STATUS_CHOICES = [("DRAFT","En préparation"),("ACTIVE","Active"),("CLOSED","Clôturée")]

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school     = models.ForeignKey(SchoolModel, on_delete=models.CASCADE, related_name="school_years")
    label      = models.CharField(max_length=20)    # ex. "2024-2025"
    start_date = models.DateField()
    end_date   = models.DateField()
    status     = models.CharField(max_length=10, choices=STATUS_CHOICES, default="DRAFT", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label    = "economat"
        db_table     = "economat_school_year"
        unique_together = [("school", "label")]
        ordering     = ["-label"]

    def __str__(self): return f"{self.school.name} — {self.label} ({self.status})"


class LevelModel(models.Model):
    PAYMENT_MODES = [("UNIQUE","Paiement unique"),("MENSUEL","Mensualités"),("TRANCHES","3 tranches")]

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school_year  = models.ForeignKey(SchoolYearModel, on_delete=models.CASCADE, related_name="levels")
    name         = models.CharField(max_length=100)
    annual_fee   = models.PositiveIntegerField()
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODES, default="TRANCHES")
    nb_months    = models.PositiveSmallIntegerField(
        default=10,
        verbose_name="Nombre de mois",
        help_text="Nombre de mensualités (pertinent uniquement si mode = Mensualités).",
    )

    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        app_label    = "economat"
        db_table     = "economat_level"
        unique_together = [("school_year", "name")]
        ordering     = ["name"]

    def __str__(self): return f"{self.name} ({self.school_year.label})"


class ClassModel(models.Model):
    id       = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    level    = models.ForeignKey(LevelModel, on_delete=models.CASCADE, related_name="classes")
    name     = models.CharField(max_length=100)
    capacity = models.PositiveSmallIntegerField(default=40)

    class Meta:
        app_label    = "economat"
        db_table     = "economat_class"
        unique_together = [("level", "name")]
        ordering     = ["name"]

    def __str__(self): return f"{self.name} ({self.level.name})"


class StudentModel(models.Model):
    """Identité permanente de l'élève. Plus de classe/niveau/statut ici."""
    RELATION_CHOICES = [
        ("PERE",   "Père"),
        ("MERE",   "Mère"),
        ("TUTEUR", "Tuteur / Tutrice"),
        ("AUTRE",  "Autre"),
    ]

    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    first_name    = models.CharField(max_length=100)
    last_name     = models.CharField(max_length=100)
    school        = models.ForeignKey(SchoolModel, on_delete=models.CASCADE, related_name="students")
    # Matricule déterministe NOM3PRENOM3-AAMMJJ-HHMMSS (généré à l'inscription).
    # null=True pour la migration des élèves existants (sera rempli via migrate).
    matricule     = models.CharField(
        max_length=30, unique=True, db_index=True,
        null=True, blank=True, default=None,
    )
    date_of_birth = models.DateField(null=True, blank=True)
    # ── Contact parent / tuteur ──────────────────────────────────────────
    parent_name     = models.CharField(max_length=200, blank=True, default="")
    parent_phone    = models.CharField(max_length=30,  blank=True, default="")
    parent_relation = models.CharField(max_length=10,  blank=True, default="",
                                       choices=RELATION_CHOICES)
    # ────────────────────────────────────────────────────────────────────
    notes         = models.TextField(blank=True, default="")
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "economat"
        db_table  = "economat_student"
        ordering  = ["last_name", "first_name"]
        indexes   = [models.Index(fields=["school"], name="idx_student_school")]

    def __str__(self):
        mat = f" [{self.matricule}]" if self.matricule else ""
        return f"{self.first_name} {self.last_name.upper()}{mat}"


class EnrollmentModel(models.Model):
    """Inscription d'un élève dans une classe pour une année scolaire donnée."""
    STATUS_CHOICES = [("ACTIVE","Actif"),("INACTIVE","Inactif"),("PROMOTED","Promu")]

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student         = models.ForeignKey(StudentModel, on_delete=models.CASCADE, related_name="enrollments")
    school_year     = models.ForeignKey(SchoolYearModel, on_delete=models.CASCADE, related_name="enrollments")
    level           = models.ForeignKey(LevelModel, on_delete=models.CASCADE, related_name="enrollments")
    klass           = models.ForeignKey(ClassModel, on_delete=models.CASCADE, related_name="enrollments",
                                        db_column="class_id")
    enrollment_date = models.DateField()
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIVE", db_index=True)
    notes           = models.TextField(blank=True, default="")
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label    = "economat"
        db_table     = "economat_enrollment"
        # Un élève ne peut être inscrit qu'une fois par année
        unique_together = [("student", "school_year")]
        ordering     = ["student__last_name", "student__first_name"]
        indexes = [
            models.Index(fields=["school_year", "status"], name="idx_enrollment_year_status"),
            models.Index(fields=["klass", "status"],       name="idx_enrollment_class_status"),
        ]

    def __str__(self): return f"{self.student} → {self.klass} ({self.school_year.label})"


class PaymentModel(models.Model):
    PAYMENT_METHODS = [
        ("ESPECES","Espèces"),("MOBILE_MONEY","Mobile Money"),
        ("VIREMENT","Virement"),("CHEQUE","Chèque"),
    ]
    PAYMENT_STATES = [("VALID","Valide"),("PENDING","En attente"),("CANCELLED","Annulé")]
    PAYMENT_CHANNELS = [("GUICHET","Guichet"),("PORTAIL_PARENT","Portail parent")]

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment     = models.ForeignKey(EnrollmentModel, on_delete=models.CASCADE, related_name="payments")
    student        = models.ForeignKey(StudentModel, on_delete=models.CASCADE,
                                       related_name="payments")  # dénormalisé
    amount         = models.PositiveIntegerField()
    payment_date   = models.DateField(db_index=True)
    method         = models.CharField(max_length=20, choices=PAYMENT_METHODS, default="ESPECES")
    # Opérateur Mobile Money (Orange Money, Wave, MTN…) — rempli seulement si method=MOBILE_MONEY.
    mobile_operator = models.CharField(max_length=40, blank=True, default="")
    # Numéro ayant servi à la transaction Mobile Money — rempli seulement si method=MOBILE_MONEY.
    mobile_number   = models.CharField(max_length=20, blank=True, default="")
    # Canal d'encaissement : au guichet par le personnel, ou en ligne par le
    # parent via le portail de paiement. Distinction affichée partout où les
    # paiements sont listés.
    channel = models.CharField(max_length=20, choices=PAYMENT_CHANNELS, default="GUICHET")
    # Référence de transaction chez la passerelle de paiement (Samirpay/CRPay) —
    # rempli uniquement pour channel=PORTAIL_PARENT, sert à interroger le statut
    # par polling (poll_status).
    gateway_transaction_ref = models.CharField(max_length=100, blank=True, default="")
    receipt_number = models.CharField(max_length=120, unique=True)
    # Libellé de la tranche visée (ex. "T1", "T2", "T3", "M1"…) — utilisé dans le numéro de reçu
    installment_label = models.CharField(max_length=20, blank=True, default="")
    recorded_by    = models.CharField(max_length=100)
    paid_by        = models.CharField(max_length=200, blank=True, default="")
    state          = models.CharField(max_length=20, choices=PAYMENT_STATES, default="VALID", db_index=True)
    notes          = models.TextField(blank=True, default="")
    # Clé d'idempotence offline : UUID généré côté navigateur avant soumission.
    # Garantit qu'un paiement offline ne peut jamais être enregistré 2 fois,
    # même si la réponse réseau se perd et que le client re-soumet.
    client_uuid    = models.UUIDField(
        null=True, blank=True, unique=True, db_index=True,
        help_text="UUID généré côté client (idempotence offline).",
    )
    # Poste de frais auquel ce paiement est imputé (non-null après migration 0014).
    fee_item    = models.ForeignKey(
        "FeeItemModel", on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="payments_for_fee",
        verbose_name="Poste de frais",
    )

    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "economat"
        db_table  = "economat_payment"
        ordering  = ["-payment_date", "-created_at"]
        indexes = [
            models.Index(fields=["enrollment", "state"],     name="idx_payment_enrollment_state"),
            models.Index(fields=["student", "payment_date"], name="idx_payment_student_date"),
        ]

    def __str__(self): return f"{self.receipt_number} | {self.amount} FCFA"



class FeeItemModel(models.Model):
    """Ligne de frais de scolarité rattachée à une année scolaire.

    Les lignes système (is_system=True) sont générées automatiquement
    depuis le tarif du niveau et ne doivent jamais être modifiées manuellement.
    """
    CATEGORY_CHOICES = [
        ("SCOLARITE",   "Scolarité"),
        ("CANTINE",     "Cantine"),
        ("TRANSPORT",   "Transport scolaire"),
        ("SORTIES",     "Sorties scolaires"),
        ("SPORT",       "Activités sportives"),
        ("FOURNITURES", "Fournitures scolaires"),
        ("AUTRE",       "Autre"),
    ]
    SCOPE_TYPE_CHOICES = [
        ("ALL",     "Toutes les classes"),
        ("CLASSES", "Classes sélectionnées"),
    ]
    PAYMENT_MODES = [
        ("UNIQUE",   "Paiement unique"),
        ("MENSUEL",  "Mensualités"),
        ("TRANCHES", "3 tranches"),
    ]

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school_year = models.ForeignKey(
        SchoolYearModel, on_delete=models.CASCADE, related_name="fee_items",
    )
    name        = models.CharField(max_length=200, verbose_name="Libellé")
    category    = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, db_index=True,
        verbose_name="Catégorie",
    )
    amount      = models.PositiveIntegerField(
        default=0, verbose_name="Montant (FCFA)",
        help_text="Montant total attendu. Pour les lignes système, synchronisé avec le tarif du niveau.",
    )
    # ── Portée ────────────────────────────────────────────────────────────────
    scope_type  = models.CharField(
        max_length=10, choices=SCOPE_TYPE_CHOICES, default="ALL",
        verbose_name="Portée",
    )
    # class_ids : liste JSON des ClassId ciblés (vide = ALL)
    class_ids   = models.JSONField(
        default=list, blank=True,
        verbose_name="Classes ciblées",
        help_text="Liste JSON de class_ids. Vide si scope_type=ALL.",
    )
    # FK niveau — conservée pour la scolarité système (is_system=True)
    level       = models.ForeignKey(
        LevelModel, on_delete=models.CASCADE, null=True, blank=True,
        related_name="fee_items", verbose_name="Niveau (scolarité système)",
    )
    # ── Paiement ──────────────────────────────────────────────────────────────
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODES, default="UNIQUE")
    nb_months    = models.PositiveSmallIntegerField(
        default=10, verbose_name="Nombre de mois",
        help_text="Nombre de mensualités (pertinent uniquement si mode = Mensualités).",
    )
    # ── Drapeaux ──────────────────────────────────────────────────────────────
    is_mandatory = models.BooleanField(default=True, verbose_name="Obligatoire")
    is_active    = models.BooleanField(default=True, db_index=True, verbose_name="Actif")
    is_system    = models.BooleanField(
        default=False, db_index=True, verbose_name="Ligne système",
        help_text="Si coché, ligne générée automatiquement (scolarité). Ne pas modifier.",
    )
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        app_label           = "economat"
        db_table            = "economat_fee_item"
        ordering            = ["category", "name"]
        verbose_name        = "Ligne de frais"
        verbose_name_plural = "Lignes de frais"
        indexes = [
            models.Index(fields=["school_year", "is_active"],  name="idx_fee_item_year_active"),
            models.Index(fields=["school_year", "category"],   name="idx_fee_item_year_category"),
            models.Index(fields=["level", "is_system"],        name="idx_fee_item_level_system"),
        ]

    def __str__(self):
        return f"{self.name} [{self.get_category_display()}] — {self.school_year.label}"




class MembershipModel(models.Model):
    ROLE_CHOICES = [("DIRECTOR","Directeur"),("SECRETARY","Secrétaire"),("ECONOME","Économe")]

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user         = models.ForeignKey("auth.User", on_delete=models.CASCADE, related_name="school_memberships")
    school       = models.ForeignKey(SchoolModel, on_delete=models.CASCADE, related_name="memberships")
    role         = models.CharField(max_length=20, choices=ROLE_CHOICES, db_index=True)
    display_name = models.CharField(max_length=200, blank=True, default="")
    login        = models.CharField(max_length=150, blank=True, default="")
    is_active    = models.BooleanField(default=True, db_index=True)
    created_by   = models.ForeignKey("auth.User", on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="created_memberships")
    joined_at    = models.DateField(auto_now_add=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label    = "economat"
        db_table     = "economat_membership"
        unique_together = [("user", "school")]
        indexes = [
            models.Index(fields=["school", "role", "is_active"], name="idx_membership_school_role"),
            models.Index(fields=["user",   "is_active"],         name="idx_membership_user_active"),
        ]

    def __str__(self): return f"{self.user.username} — {self.role} @ {self.school.name}"


class SchoolRegistrationModel(models.Model):
    """
    Demande d'inscription d'une école sur la plateforme.

    Cycle de vie :
      PENDING    → La demande est soumise, en attente de validation interne.
      ACTIVATED  → Validée : école + compte directeur créés, email envoyé.
      REJECTED   → Rejetée manuellement (notes internes).

    À l'activation, les champs created_school / activated_user sont remplis
    pour conserver le lien entre la demande et les entités créées.
    """
    STATUS_PENDING   = "PENDING"
    STATUS_ACTIVATED = "ACTIVATED"
    STATUS_REJECTED  = "REJECTED"
    STATUS_CHOICES = [
        (STATUS_PENDING,   "En attente"),
        (STATUS_ACTIVATED, "Activée"),
        (STATUS_REJECTED,  "Rejetée"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Clé d'idempotence générée côté navigateur avant soumission.
    # Garantit qu'une re-soumission (coupure réseau) ne crée pas de doublon.
    client_uuid = models.UUIDField(
        null=True, blank=True, unique=True, db_index=True,
        help_text="UUID généré côté client (idempotence anti-doublon).",
    )

    # ── Informations sur l'école ──────────────────────────────────────────────
    school_name = models.CharField(max_length=200, verbose_name="Nom de l'école")
    city        = models.CharField(max_length=100, verbose_name="Ville")
    country     = models.ForeignKey(
        CountryModel,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="registrations",
        verbose_name="Pays",
    )

    # ── Informations sur le gérant ────────────────────────────────────────────
    manager_first_name = models.CharField(max_length=100, verbose_name="Prénom du gérant")
    manager_last_name  = models.CharField(max_length=100, verbose_name="Nom du gérant")
    manager_email      = models.EmailField(verbose_name="Email du gérant")
    manager_phone      = models.CharField(max_length=30, blank=True, default="",
                                          verbose_name="Téléphone du gérant")

    # ── Moyens d'encaissement souhaités ──────────────────────────────────────
    # Liste JSON des méthodes choisies, ex. ["ESPECES", "MOBILE_MONEY"]
    payment_methods = models.JSONField(
        default=list, blank=True,
        verbose_name="Moyens d'encaissement",
        help_text='Liste JSON, ex. ["ESPECES", "MOBILE_MONEY"]',
    )
    # Rempli seulement si MOBILE_MONEY est sélectionné
    mobile_operator = models.CharField(max_length=60, blank=True, default="",
                                       verbose_name="Opérateur Mobile Money")
    mobile_number   = models.CharField(max_length=30, blank=True, default="",
                                       verbose_name="Numéro Mobile Money")

    # ── Statut & traçabilité ──────────────────────────────────────────────────
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES,
        default=STATUS_PENDING, db_index=True,
        verbose_name="Statut",
    )
    notes = models.TextField(
        blank=True, default="",
        verbose_name="Notes internes",
        help_text="Commentaires de validation (visibles seulement en admin).",
    )

    # ── Liens vers les entités créées à l'activation ─────────────────────────
    created_school  = models.ForeignKey(
        "SchoolModel", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="registration",
        verbose_name="École créée",
    )
    activated_user  = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="school_registration",
        verbose_name="Compte créé",
    )

    created_at   = models.DateTimeField(auto_now_add=True, verbose_name="Soumise le")
    activated_at = models.DateTimeField(null=True, blank=True, verbose_name="Activée le")

    class Meta:
        app_label           = "economat"
        db_table            = "economat_school_registration"
        ordering            = ["-created_at"]
        verbose_name        = "Demande d'inscription"
        verbose_name_plural = "Demandes d'inscription"
        indexes = [
            models.Index(fields=["status", "created_at"], name="idx_registration_status_date"),
            models.Index(fields=["manager_email"],         name="idx_registration_email"),
        ]

    def __str__(self):
        return f"{self.school_name} ({self.city}) — {self.get_status_display()}"


class PotentialCustomerModel(models.Model):
    """
    Client potentiel : personne intéressée par Sukulu dont le pays n'est pas
    encore géré sur la plateforme.

    Enregistré depuis la page publique « Autres pays » — un email suffit.
    Les doublons sont autorisés : chaque soumission crée une ligne indépendante.
    """
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email        = models.EmailField(verbose_name="Email")
    country_name = models.CharField(
        max_length=100, blank=True, default="",
        verbose_name="Pays",
        help_text="Nom du pays saisi librement par l'internaute.",
    )
    created_at   = models.DateTimeField(auto_now_add=True, verbose_name="Enregistré le")

    class Meta:
        app_label           = "economat"
        db_table            = "economat_potential_customer"
        ordering            = ["-created_at"]
        verbose_name        = "Client potentiel"
        verbose_name_plural = "Clients potentiels"
        indexes = [
            models.Index(fields=["email"],      name="idx_potential_email"),
            models.Index(fields=["created_at"], name="idx_potential_created_at"),
        ]

    def __str__(self):
        suffix = f" ({self.country_name})" if self.country_name else ""
        return f"{self.email}{suffix}"


class OfflineCredentialModel(models.Model):
    """
    Verifier PBKDF2 dédié pour l'authentification offline.

    Séparé du hash Django (auth_user.password) pour isoler les usages :
    - Ce verifier ne permet PAS de se connecter côté serveur.
    - Il sert uniquement à déverrouiller le shell PWA en cache, localement.
    - Sel propre (offline_salt) ≠ sel du hash Django → compromis de ce champ
      ne compromet pas le mot de passe serveur.
    - expires_at : 30 jours glissants, renouvelé à chaque connexion en ligne.
    - failed_attempts : limite à 5 essais offline (anti-brute-force local).
    """
    user           = models.OneToOneField(
        "auth.User", on_delete=models.CASCADE,
        related_name="offline_credential",
    )
    # Hash PBKDF2 calculé côté serveur : format "algorithm$iterations$salt$hash"
    # Ne jamais exposer dans une API publique.
    verifier       = models.CharField(max_length=256)
    # Sel indépendant (base64, 16 bytes) utilisé pour le verifier
    offline_salt   = models.CharField(max_length=64)
    iterations     = models.PositiveIntegerField(default=200_000)
    expires_at     = models.DateTimeField()
    # Compteur d'échecs offline (reset à 0 après connexion en ligne réussie)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "economat"
        db_table  = "economat_offline_credential"

    def __str__(self):
        return f"OfflineCred({self.user.username}, expires={self.expires_at.date()})"
