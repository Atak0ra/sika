"""
application/dto.py — Commands + Results (NOUVEAU SCHEMA).
"""
from __future__ import annotations
import datetime
from dataclasses import dataclass, field
from typing import List, Optional


# ─ School Year ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CreateSchoolYearCommand:
    school_id:  str
    label:      str         # ex. "2025-2026"
    start_date: datetime.date
    end_date:   datetime.date
    duplicate_from_year_id: Optional[str] = None  # dupliquer la structure d'une année précédente

@dataclass(frozen=True)
class ActivateSchoolYearCommand:
    school_id: str
    year_id:   str

@dataclass(frozen=True)
class CloseSchoolYearCommand:
    school_id: str
    year_id:   str

@dataclass
class SchoolYearResult:
    success:      bool
    year_id:      Optional[str] = None
    label:        Optional[str] = None
    status:       Optional[str] = None
    error_message: Optional[str] = None


# ─ Level + Class ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AddLevelCommand:
    school_id:       str
    year_id:         str
    user_id:         str
    level_name:      str
    annual_fee_fcfa: int = 0
    payment_mode:    str = "TRANCHES"
    nb_months:       int = 10

@dataclass(frozen=True)
class AddClassCommand:
    school_id:  str
    year_id:    str
    level_id:   str
    user_id:    str
    class_name: str
    capacity:   int = 40

@dataclass
class AddLevelResult:
    success:       bool
    level_id:      Optional[str] = None
    level_name:    Optional[str] = None
    error_message: Optional[str] = None

@dataclass
class AddClassResult:
    success:       bool
    class_id:      Optional[str] = None
    class_name:    Optional[str] = None
    level_name:    Optional[str] = None
    error_message: Optional[str] = None


# ─ Pricing ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ConfigureSchoolPricingCommand:
    school_id:       str
    year_id:         str
    level_id:        str
    annual_fee_fcfa: int
    payment_mode:    str
    nb_months:       int = 10

@dataclass
class ConfigurePricingResult:
    success:       bool
    level_name:    Optional[str] = None
    new_fee_fcfa:  Optional[int] = None
    payment_mode:  Optional[str] = None
    error_message: Optional[str] = None


# ─ Student (identité) ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RegisterStudentCommand:
    """Crée l'identité Student ET l'Enrollment en une seule commande."""
    first_name:      str
    last_name:       str
    school_id:       str
    year_id:         str
    level_id:        str
    class_id:        str
    date_of_birth:   Optional[datetime.date] = None
    enrollment_date: Optional[datetime.date] = None
    notes:           str = ""
    parent_name:     str = ""
    parent_phone:    str = ""
    parent_relation: str = ""

@dataclass
class RegisterStudentResult:
    success:       bool
    student_id:    Optional[str] = None
    enrollment_id: Optional[str] = None
    student_name:  Optional[str] = None
    class_name:    Optional[str] = None
    level_name:    Optional[str] = None
    error_message: Optional[str] = None


# ─ Enrollment + Promotion en masse ───────────────────────────────────────────

@dataclass(frozen=True)
class PromoteClassCommand:
    """Réinscrit en masse les élèves d'une classe vers une nouvelle année."""
    director_user_id:   str
    from_year_id:       str    # année source
    to_year_id:         str    # année cible
    from_class_id:      str    # classe source
    to_class_id:        str    # classe cible (nouvelle année)
    excluded_student_ids: List[str] = field(default_factory=list)  # élèves à exclure

@dataclass
class PromoteClassResult:
    success:        bool
    promoted_count: int = 0
    skipped_count:  int = 0
    error_message:  Optional[str] = None


# ─ Payment ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RecordPaymentCommand:
    student_id:        str
    year_id:           str    # année scolaire concernée
    amount_fcfa:       int
    payment_date:      datetime.date
    method:            str
    recorded_by:       str
    notes:             str = ""
    paid_by:           str = ""
    # Poste de frais visé — obligatoire. Pointe vers un FeeItemModel.id.
    # La ligne scolarité (système) a son propre fee_item_id.
    fee_item_id:       str = ""
    # Opérateur Mobile Money (Orange Money, Wave, MTN…) — pertinent seulement
    # si method == "MOBILE_MONEY".
    mobile_operator:   str = ""
    # Numéro ayant servi à la transaction — pertinent seulement si method == "MOBILE_MONEY".
    mobile_number:     str = ""
    # ── Portail de paiement parent ────────────────────────────────────────
    initial_state:     str = "VALID"
    channel:           str = ""
    gateway_transaction_ref: str = ""
    # ── Champs offline / déterministes ───────────────────────────────────
    receipt_number:    str = ""
    installment_label: str = ""
    client_uuid:       str = ""

@dataclass
class RecordPaymentResult:
    success:         bool
    payment_id:      Optional[str] = None
    receipt_number:  Optional[str] = None
    student_name:    Optional[str] = None
    amount_paid:     Optional[int] = None
    new_balance:     Optional[int] = None
    payment_status:  Optional[str] = None
    class_name:      Optional[str] = None
    level_name:      Optional[str] = None
    fee_item_name:   Optional[str] = None
    fee_category:    Optional[str] = None
    receipt_rows:    Optional[dict] = None
    error_message:   Optional[str] = None


# ─ FeeItem ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CreateFeeItemCommand:
    """Créer une ligne de frais manuelle (hors scolarité système)."""
    school_year_id: str
    name:           str
    category:       str          # FeeCategory.value (hors SCOLARITE)
    amount_fcfa:    int
    scope_type:     str          # "ALL" ou "CLASSES"
    class_ids:      list = None  # liste de ClassId.value si scope_type=CLASSES
    payment_mode:   str = "UNIQUE"
    nb_months:      int = 10
    is_mandatory:   bool = True
    created_by:     str = ""

    def __post_init__(self):
        # normalise None → liste vide
        object.__setattr__(self, "class_ids", list(self.class_ids or []))

@dataclass(frozen=True)
class UpdateFeeItemCommand:
    """Modifier une ligne de frais manuelle existante."""
    fee_item_id:  str
    name:         str
    amount_fcfa:  int
    payment_mode: str
    nb_months:    int
    is_mandatory: bool
    updated_by:   str = ""

@dataclass(frozen=True)
class DeactivateFeeItemCommand:
    """Archiver une ligne de frais manuelle (ne plus apparaître à payer)."""
    fee_item_id: str
    updated_by:  str = ""

@dataclass
class FeeItemResult:
    success:       bool
    fee_item_id:   Optional[str] = None
    name:          Optional[str] = None
    category:      Optional[str] = None
    error_message: Optional[str] = None


# ─ Payable Items (liste de frais dus + payés pour un élève) ───────────────────

@dataclass(frozen=True)
class PayableLine:
    """Une ligne de frais dans la liste « à payer » d'un élève.

    Alimente le dropdown guichet ET la sélection parent sur mobile.
    """
    fee_item_id:    str            # FeeItemId.value (permet l'imputation d'un paiement)
    name:           str            # Libellé à afficher ("Scolarité", "Cantine T1"…)
    category:       str            # FeeCategory.value (pour le regroupement)
    category_label: str            # FeeCategory.label (pour l'affichage)
    amount_due:     int            # Montant total attendu (FCFA)
    amount_paid:    int            # Total déjà payé (paiements VALID)
    remaining:      int            # Reste à payer (>= 0)
    payment_mode:   str            # PaymentMode.value (informatif)
    is_system:      bool           # True = scolarité auto-générée
    is_mandatory:   bool
    next_due_label: Optional[str] = None   # Prochaine échéance (ex. "Tranche 2")
    next_due_date:  Optional[str] = None   # ISO date de la prochaine échéance
    payment_status: Optional[str] = None   # PaymentStatus.value

@dataclass
class PayableItemsResult:
    success:       bool
    lines:         List[PayableLine] = field(default_factory=list)
    total_due:     int = 0
    total_paid:    int = 0
    total_remaining: int = 0
    error_message: Optional[str] = None



@dataclass(frozen=True)
class CancelPaymentCommand:
    payment_id:       str
    school_id:        str
    director_user_id: str
    reason:           str = ""

@dataclass
class CancelPaymentResult:
    success:        bool
    payment_id:     Optional[str] = None
    receipt_number: Optional[str] = None
    error_message:  Optional[str] = None
