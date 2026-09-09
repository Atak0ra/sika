"""
application/ports/llm_port.py
================================
PORT SORTANT — Interface du connecteur LLM (IA).

Ce port abstrait découple le use case AskDirectorChatQuery
de la technologie LLM concrète (Groq, OpenAI, local Ollama…).

L'infrastructure fournit l'implémentation (GroqLLMAdapter).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class ChatMessage:
    """Un message dans l'historique de conversation."""
    role: str    # "user" | "assistant"
    content: str


@dataclass
class LLMQueryResult:
    """Résultat retourné par le port LLM."""
    intent: str                    # "analytical" | "conversational"
    chat_reply: Optional[str]      # Réponse directe si conversationnel
    sql: str = ""                  # SQL généré (si analytique)
    columns: List[str] = field(default_factory=list)
    rows: List[tuple] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    @property
    def is_analytical(self) -> bool:
        return self.intent == "analytical"


class LLMPort(ABC):
    """Port sortant : connecteur vers un modèle de langage.

    Usage dans AskDirectorChatQuery :
        result = self._llm.answer(
            question="Combien d'élèves en retard de paiement ?",
            db_path="/path/to/db.sqlite3",
            table="economat_payment",
        )
    """

    @abstractmethod
    def answer(
        self,
        question: str,
        db_path: str,
        table: Optional[str] = None,
        history: Optional[List[ChatMessage]] = None,
        system_context: Optional[str] = None,
    ) -> LLMQueryResult:
        """Traduit une question en SQL, l'exécute et retourne les données.

        Args:
            question       : question en langage naturel (directeur).
            db_path        : chemin vers la base SQLite à interroger.
            table          : table principale à interroger (auto si None).
            history        : historique de la conversation (pour le contexte).
            system_context : contexte métier injecté dans le prompt système.
        """
