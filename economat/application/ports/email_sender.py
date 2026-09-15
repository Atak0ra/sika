"""
application/ports/email_sender.py
===================================
Port sortant — interface d'envoi d'email transactionnel.
"""
from __future__ import annotations
from abc import ABC, abstractmethod


class EmailSender(ABC):

    @abstractmethod
    def send(self, *, to: str, subject: str, html: str) -> None:
        """
        Envoie un email transactionnel.

        Lève une exception (EmailSendError) en cas d'échec.
        """


class EmailSendError(Exception):
    """Levée quand l'envoi d'email échoue (erreur réseau, API, config)."""
