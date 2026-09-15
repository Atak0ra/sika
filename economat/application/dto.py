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
    # Opérateur Mobile Money (Orange Money, Wave, MTN…) — pertinent seulement
    # si method == "MOBILE_MONEY".
    mobile_operator:   str = ""
    # Numéro ayant servi à la transaction — pertinent seulement si method == "MOBILE_MONEY".
    mobile_number:     str = ""
    # ── Portail de paiement parent ────────────────────────────────────────
    # État initial du paiement créé. "VALID" (défaut, comportement guichet
    # inchangé) ou "PENDING" (paiement en ligne, en attente de confirmation
    # de la passerelle avant de compter dans un solde).
    initial_state:     str = "VALID"
    # Canal d'encaissement : "" (défaut → GUICHET côté modèle) ou
    # "PORTAIL_PARENT" pour un paiement fait par le parent en ligne.
    channel:           str = ""
    # Référence de transaction chez la passerelle de paiement (Samirpay/CRPay),
    # pertinent seulement pour un paiement portail.
    gateway_transaction_ref: str = ""
    # ── Champs offline / déterministes ───────────────────────────────────
    # receipt_number fourni : généré côté client (déterministe) ou laissé vide
    # pour que le serveur le génère en fallback (mode online classique).
    receipt_number:    str = ""
    # Tranche visée (ex. "T1", "T2", "T3", "M1"…) — incluse dans le numéro de reçu.
    installment_label: str = ""
    # UUID idempotence : si fourni, le paiement ne sera enregistré qu'une fois.
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
    receipt_rows:    Optional[dict] = None
    error_message:   Optional[str] = None


# ─ Cancel Payment ────────────────────────────────────────────────────────────────────

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
