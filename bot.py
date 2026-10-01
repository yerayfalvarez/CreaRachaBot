"""Bot de Telegram para el control de suplementación con creatina.

Comandos: /start, /tomada y /racha, más un recordatorio diario automático
a una hora configurable para quienes aún no han registrado la toma.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Forbidden, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from database import Database, StreakStats

logger = logging.getLogger(__name__)

TAKEN_CALLBACK = "creatine_taken"


# ---------------------------------------------------------------------- #
# Configuración
# ---------------------------------------------------------------------- #
@dataclass(frozen=True)
class Config:
    """Configuración cargada desde variables de entorno."""

    token: str
    timezone: ZoneInfo
    reminder_time: time  # con tzinfo
    db_path: str


def load_config() -> Config:
    """Lee y valida la configuración del archivo ``.env``.

    Raises:
        RuntimeError: Si falta el token o algún valor es inválido.
    """
    load_dotenv()

    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Falta TELEGRAM_TOKEN. Copia .env.example a .env y complétalo.")

    tz_name = os.getenv("TIMEZONE", "Europe/Madrid")
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"Zona horaria inválida: {tz_name!r}") from exc

    raw_time = os.getenv("REMINDER_TIME", "10:00")
    try:
        parsed = datetime.strptime(raw_time, "%H:%M").time()
    except ValueError as exc:
        raise RuntimeError(f"REMINDER_TIME debe tener formato HH:MM, recibido {raw_time!r}") from exc

    return Config(
        token=token,
        timezone=tz,
        reminder_time=parsed.replace(tzinfo=tz),
        db_path=os.getenv("DB_PATH", "creatine.db"),
    )


# ---------------------------------------------------------------------- #
# Utilidades
# ---------------------------------------------------------------------- #
def _config(context: ContextTypes.DEFAULT_TYPE) -> Config:
    return context.bot_data["config"]  # type: ignore[no-any-return]


def _db(context: ContextTypes.DEFAULT_TYPE) -> Database:
    return context.bot_data["db"]  # type: ignore[no-any-return]


def _today(context: ContextTypes.DEFAULT_TYPE) -> date:
    """Fecha de hoy en la zona horaria configurada."""
    return datetime.now(_config(context).timezone).date()


def _days(n: int) -> str:
    return f"{n} día" if n == 1 else f"{n} días"


def _milestone(streak: int) -> str:
    """Mensaje motivacional en hitos de racha."""
    if streak in (7, 30, 100, 365):
        return f"\n🎉 ¡Hito desbloqueado: {_days(streak)} seguidos!"
    return ""


def _reminder_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Ya la tomé", callback_data=TAKEN_CALLBACK)]]
    )


async def record_intake(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> str:
    """Registra la toma de hoy y devuelve el mensaje de respuesta.

    Lógica compartida por el comando ``/tomada`` y el botón del recordatorio.
    """
    db = _db(context)
    today = _today(context)
    is_new = await db.register_intake(chat_id, today)
    stats = await db.get_stats(chat_id, today)

    if not is_new:
        return (
            "Ya habías registrado tu creatina hoy ✅\n"
            f"🔥 Racha actual: {_days(stats.current)}"
        )
    return (
        "💪 ¡Creatina registrada!\n"
        f"🔥 Racha actual: {_days(stats.current)}{_milestone(stats.current)}"
    )


def format_stats(stats: StreakStats) -> str:
    """Construye el texto del comando ``/racha``."""
    if stats.total == 0:
        return "Aún no tienes tomas registradas. Usa /tomada cuando tomes tu creatina 💪"

    lines = [
        f"🔥 Racha actual: {_days(stats.current)}",
        f"🏆 Mejor racha: {_days(stats.longest)}",
        f"📅 Tomas totales: {stats.total}",
    ]
    if not stats.taken_today and stats.current > 0:
        lines.append("\n⚠️ Hoy aún no la has tomado. ¡No pierdas la racha!")
    return "\n".join(lines)


# ---------------------------------------------------------------------- #
# Handlers
# ---------------------------------------------------------------------- #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """``/start``: da de alta al usuario y explica los comandos."""
    chat, message = update.effective_chat, update.message
    if chat is None or message is None:
        return

    is_new = await _db(context).add_user(chat.id)
    hour = _config(context).reminder_time.strftime("%H:%M")
    greeting = "¡Bienvenido! 👋" if is_new else "¡Qué bueno verte de nuevo! 👋"
    await message.reply_text(
        f"{greeting}\n\n"
        "Te ayudo a mantener la constancia con tu creatina.\n\n"
        "/tomada — registra la toma de hoy\n"
        "/racha — consulta tu racha\n\n"
        f"Cada día a las {hour} te recordaré tomarla si aún no la has registrado."
    )


async def tomada(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """``/tomada``: registra la toma de hoy."""
    chat, message = update.effective_chat, update.message
    if chat is None or message is None:
        return
    await message.reply_text(await record_intake(context, chat.id))


async def racha(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """``/racha``: muestra la racha actual y otras estadísticas."""
    chat, message = update.effective_chat, update.message
    if chat is None or message is None:
        return
    stats = await _db(context).get_stats(chat.id, _today(context))
    await message.reply_text(format_stats(stats))


async def on_taken_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Botón «Ya la tomé» del recordatorio."""
    query, chat = update.callback_query, update.effective_chat
    if query is None or chat is None:
        return
    await query.answer()
    await query.edit_message_text(await record_intake(context, chat.id))


async def send_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job diario: avisa a quienes aún no han registrado la toma de hoy."""
    pending = await _db(context).get_pending_users(_today(context))
    logger.info("Enviando recordatorios a %d usuario(s)", len(pending))

    for chat_id in pending:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⏰ ¡Hora de tu creatina! Aún no la has registrado hoy.",
                reply_markup=_reminder_keyboard(),
            )
        except Forbidden:
            logger.warning("El usuario %s bloqueó el bot; se omite.", chat_id)
        except TelegramError:
            logger.exception("No se pudo enviar el recordatorio a %s", chat_id)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registra errores no controlados y avisa al usuario sin exponer detalles."""
    logger.error("Excepción no controlada", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat is not None:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="😕 Algo salió mal. Inténtalo de nuevo en unos minutos.",
            )
        except TelegramError:
            logger.exception("No se pudo notificar el error al usuario")


# ---------------------------------------------------------------------- #
# Arranque
# ---------------------------------------------------------------------- #
def main() -> None:
    """Punto de entrada: configura la aplicación y arranca el polling."""
    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    config = load_config()
    db = Database(config.db_path)
    db.init()

    application = Application.builder().token(config.token).build()
    application.bot_data["config"] = config
    application.bot_data["db"] = db

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("tomada", tomada))
    application.add_handler(CommandHandler("racha", racha))
    application.add_handler(CallbackQueryHandler(on_taken_button, pattern=f"^{TAKEN_CALLBACK}$"))
    application.add_error_handler(error_handler)

    if application.job_queue is None:
        raise RuntimeError(
            "JobQueue no disponible. Instala: pip install 'python-telegram-bot[job-queue]'"
        )
    application.job_queue.run_daily(
        send_reminders,
        time=config.reminder_time,
        name="daily_creatine_reminder",
    )

    logger.info(
        "Bot iniciado. Recordatorio diario a las %s (%s)",
        config.reminder_time.strftime("%H:%M"),
        config.timezone.key,
    )
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()