"""
Management command : generate_transactions

Génère des transactions réalistes en masse avec Faker + bulk_create.

Usage :
    python manage.py generate_transactions          # 1 000 (défaut)
    python manage.py generate_transactions 10000    # 10 000
    python manage.py generate_transactions 100000   # 100 000
    python manage.py generate_transactions 50000 --clear  # vide avant
"""

import random
import uuid
from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction as db_transaction
from faker import Faker

from analytics.models import Transaction

fake = Faker(["fr_FR", "en_US", "ar_AA", "de_DE", "es_ES"])

# ── Données de référence ──────────────────────────────────────────────────────

COUNTRIES = [
    "France", "Sénégal", "Maroc", "Côte d'Ivoire", "Mali",
    "Guinée", "Cameroun", "Tunisie", "Algérie", "Madagascar",
    "Espagne", "Italie", "Allemagne", "Belgique", "Canada",
    "États-Unis", "Royaume-Uni", "Suisse", "Portugal", "Mauritanie",
]

CURRENCIES = {
    "France": "EUR", "Sénégal": "XOF", "Maroc": "MAD",
    "Côte d'Ivoire": "XOF", "Mali": "XOF", "Guinée": "GNF",
    "Cameroun": "XAF", "Tunisie": "TND", "Algérie": "DZD",
    "Madagascar": "MGA", "Espagne": "EUR", "Italie": "EUR",
    "Allemagne": "EUR", "Belgique": "EUR", "Canada": "CAD",
    "États-Unis": "USD", "Royaume-Uni": "GBP", "Suisse": "CHF",
    "Portugal": "EUR", "Mauritanie": "MRU",
}

EXCHANGE_RATES = {
    ("EUR", "XOF"): 655.96, ("EUR", "MAD"): 10.85, ("EUR", "GNF"): 9500.0,
    ("EUR", "XAF"): 655.96, ("EUR", "TND"): 3.35, ("EUR", "DZD"): 145.0,
    ("EUR", "MGA"): 4850.0, ("EUR", "MRU"): 43.5, ("EUR", "CAD"): 1.47,
    ("EUR", "USD"): 1.08, ("EUR", "GBP"): 0.86, ("EUR", "CHF"): 0.96,
    ("USD", "XOF"): 607.0, ("USD", "MAD"): 10.02, ("GBP", "XOF"): 760.0,
}

AGENTS = [
    "Orange Money", "Western Union", "MoneyGram", "Wave",
    "WorldRemit", "CashExpress", "Ria Money", "Transfert Express",
    "SFM Money", "Lydia Pro", "Wise Transfer", "PayGo Africa",
]

# Pondéré : majoritairement completed
STATUSES = [
    Transaction.Status.COMPLETED,
    Transaction.Status.COMPLETED,
    Transaction.Status.COMPLETED,
    Transaction.Status.PENDING,
    Transaction.Status.CANCELLED,
    Transaction.Status.SUSPENDED,
]


def _get_exchange_rate(send_cur: str, payout_cur: str) -> float:
    if send_cur == payout_cur:
        return round(1.0 + random.uniform(-0.001, 0.001), 6)
    key = (send_cur, payout_cur)
    rev_key = (payout_cur, send_cur)
    if key in EXCHANGE_RATES:
        base = EXCHANGE_RATES[key]
    elif rev_key in EXCHANGE_RATES:
        base = 1 / EXCHANGE_RATES[rev_key]
    else:
        base = random.uniform(0.5, 800.0)
    return round(base * random.uniform(0.98, 1.02), 6)


def _build_transaction(start_date: datetime, end_date: datetime) -> Transaction:
    """Construit une instance Transaction non-sauvegardée."""
    src = random.choice(COUNTRIES)
    dst = random.choice([c for c in COUNTRIES if c != src])
    send_cur = CURRENCIES[src]
    payout_cur = CURRENCIES[dst]
    amount = round(random.uniform(10.0, 5000.0), 2)
    commission = round(amount * random.uniform(0.005, 0.04), 2)
    delta = end_date - start_date
    random_seconds = random.randint(0, int(delta.total_seconds()))
    created_at = start_date + timedelta(seconds=random_seconds)

    return Transaction(
        id=uuid.uuid4(),
        sender_name=fake.name(),
        receiver_name=fake.name(),
        source_country=src,
        destination_country=dst,
        agent_name=random.choice(AGENTS),
        amount=amount,
        commission=commission,
        send_currency=send_cur,
        payout_currency=payout_cur,
        exchange_rate=_get_exchange_rate(send_cur, payout_cur),
        status=random.choice(STATUSES),
        created_at=created_at,
    )


class Command(BaseCommand):
    help = "Génère des transactions réalistes en masse (Faker + bulk_create)."

    def add_arguments(self, parser):
        parser.add_argument(
            "count", type=int, nargs="?", default=1_000,
            help="Nombre de transactions à générer (défaut : 1 000).",
        )
        parser.add_argument(
            "--clear", action="store_true",
            help="Vide la table Transaction avant de générer.",
        )
        parser.add_argument(
            "--batch-size", type=int, default=5_000,
            help="Taille des lots pour bulk_create (défaut : 5 000).",
        )

    def handle(self, *args, **options):
        count = options["count"]
        batch_size = options["batch_size"]

        if count < 1:
            raise CommandError("Le nombre de transactions doit être ≥ 1.")
        if count > 500_000:
            raise CommandError("Maximum 500 000 transactions par commande.")

        now = datetime.now(tz=timezone.utc)
        start_date = now - timedelta(days=548)  # ~18 mois

        if options["clear"]:
            deleted, _ = Transaction.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"🗑  {deleted:,} transaction(s) supprimée(s)."))

        self.stdout.write(f"⚙️  Génération de {count:,} transactions (batch={batch_size:,}) …")

        total_created = 0
        remaining = count

        while remaining > 0:
            current_batch = min(batch_size, remaining)
            txs = [_build_transaction(start_date, now) for _ in range(current_batch)]
            with db_transaction.atomic():
                Transaction.objects.bulk_create(txs, batch_size=current_batch)
            total_created += current_batch
            remaining -= current_batch
            pct = (total_created / count) * 100
            self.stdout.write(f"  ✓ {total_created:>8,} / {count:,}  ({pct:.1f}%)")

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅ {total_created:,} transactions générées !\n"
                f"   Période couverte : {start_date.strftime('%d/%m/%Y')} → {now.strftime('%d/%m/%Y')}"
            )
        )
