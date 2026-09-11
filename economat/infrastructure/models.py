"""
infrastructure/models.py
==========================
Modèles ORM — NOUVEAU SCHEMA avec année scolaire comme racine temporelle.

Hiérarchie des tables :
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


class SchoolModel(models.Model):
    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name           = models.CharField(max_length=200)
    city           = models.CharField(max_length=100)
    country        = models.CharField(max_length=100, default="Sénégal")
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
    PAYMENT_STATES = [("VALID","Valide"),("CANCELLED","Annulé")]

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    enrollment     = models.ForeignKey(EnrollmentModel, on_delete=models.CASCADE, related_name="payments")
    student        = models.ForeignKey(StudentModel, on_delete=models.CASCADE,
                                       related_name="payments")  # dénormalisé
    amount         = models.PositiveIntegerField()
    payment_date   = models.DateField(db_index=True)
    method         = models.CharField(max_length=20, choices=PAYMENT_METHODS, default="ESPECES")
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
