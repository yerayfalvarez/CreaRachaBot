"""Capa de persistencia del bot (SQLite).

``sqlite3`` es síncrono, por lo que todas las operaciones públicas son
corrutinas que delegan el trabajo en un hilo con ``asyncio.to_thread`` para
no bloquear el event loop de Telegram. Cada operación abre su propia
conexión, lo que la hace segura entre hilos.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    chat_id    INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS intakes (
    chat_id  INTEGER NOT NULL,
    taken_on TEXT    NOT NULL,              -- fecha ISO (YYYY-MM-DD)
    PRIMARY KEY (chat_id, taken_on),        -- una toma por usuario y día
    FOREIGN KEY (chat_id) REFERENCES users (chat_id) ON DELETE CASCADE
);
"""


class DatabaseError(Exception):
    """Error de persistencia independiente del motor subyacente."""


@dataclass(frozen=True)
class StreakStats:
    """Resumen de estadísticas de un usuario."""

    current: int
    longest: int
    total: int
    taken_today: bool


def calculate_current_streak(days: set[date], today: date) -> int:
    """Calcula los días consecutivos que terminan hoy (o ayer).

    Si el usuario aún no ha registrado la toma de hoy, la racha se mantiene
    viva contando desde ayer; solo se pierde si ayer tampoco hubo toma.

    Args:
        days: Conjunto de fechas con toma registrada.
        today: Fecha actual en la zona horaria del bot.

    Returns:
        Número de días consecutivos de la racha actual.
    """
    cursor = today if today in days else today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def calculate_longest_streak(days: set[date]) -> int:
    """Calcula la racha consecutiva más larga de todo el histórico."""
    longest = current = 0
    previous: date | None = None
    for day in sorted(days):
        if previous is not None and day - previous == timedelta(days=1):
            current += 1
        else:
            current = 1
        longest = max(longest, current)
        previous = day
    return longest


class Database:
    """Acceso asíncrono a la base de datos SQLite del bot."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)

    # ------------------------------------------------------------------ #
    # Infraestructura
    # ------------------------------------------------------------------ #
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    async def _run(self, func: Callable[..., T], *args: object) -> T:
        """Ejecuta ``func`` en un hilo traduciendo errores de SQLite."""
        try:
            return await asyncio.to_thread(func, *args)
        except sqlite3.Error as exc:
            logger.exception("Error de base de datos")
            raise DatabaseError(str(exc)) from exc

    def init(self) -> None:
        """Crea las tablas si no existen (llamar una vez al arrancar)."""
        try:
            with closing(self._connect()) as conn:
                conn.executescript(SCHEMA)
        except sqlite3.Error as exc:
            raise DatabaseError(f"No se pudo inicializar la base de datos: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Implementaciones síncronas
    # ------------------------------------------------------------------ #
    def _add_user_sync(self, chat_id: int) -> bool:
        with closing(self._connect()) as conn, conn:
            cur = conn.execute("INSERT OR IGNORE INTO users (chat_id) VALUES (?)", (chat_id,))
            return cur.rowcount == 1

    def _register_intake_sync(self, chat_id: int, day: date) -> bool:
        with closing(self._connect()) as conn, conn:
            conn.execute("INSERT OR IGNORE INTO users (chat_id) VALUES (?)", (chat_id,))
            cur = conn.execute(
                "INSERT OR IGNORE INTO intakes (chat_id, taken_on) VALUES (?, ?)",
                (chat_id, day.isoformat()),
            )
            return cur.rowcount == 1

    def _get_days_sync(self, chat_id: int) -> set[date]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT taken_on FROM intakes WHERE chat_id = ?", (chat_id,)
            ).fetchall()
        return {date.fromisoformat(row[0]) for row in rows}

    def _get_pending_sync(self, day: date) -> list[int]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT chat_id FROM users
                WHERE chat_id NOT IN (SELECT chat_id FROM intakes WHERE taken_on = ?)
                """,
                (day.isoformat(),),
            ).fetchall()
        return [row[0] for row in rows]

    # ------------------------------------------------------------------ #
    # API pública asíncrona
    # ------------------------------------------------------------------ #
    async def add_user(self, chat_id: int) -> bool:
        """Registra un usuario. Devuelve ``True`` si es nuevo."""
        return await self._run(self._add_user_sync, chat_id)

    async def register_intake(self, chat_id: int, day: date) -> bool:
        """Registra la toma de ``day``.

        Returns:
            ``True`` si se registró ahora; ``False`` si ya existía.
        """
        return await self._run(self._register_intake_sync, chat_id, day)

    async def get_stats(self, chat_id: int, today: date) -> StreakStats:
        """Devuelve racha actual, mejor racha, total de tomas y estado de hoy."""
        days = await self._run(self._get_days_sync, chat_id)
        return StreakStats(
            current=calculate_current_streak(days, today),
            longest=calculate_longest_streak(days),
            total=len(days),
            taken_today=today in days,
        )

    async def get_pending_users(self, day: date) -> list[int]:
        """Lista los usuarios que aún no han registrado la toma de ``day``."""
        return await self._run(self._get_pending_sync, day)
