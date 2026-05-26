import asyncio
import time
from contextlib import asynccontextmanager, suppress
from typing import Dict, Optional, Tuple

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import src.keyboards as kb
from config import config, get_config
from src.services.request_manager import request_manager
from src.utils.session import session_store

# Минимальная пауза между edit'ами одного сообщения (Telegram дросселирует ~30/min)
STREAM_EDIT_INTERVAL = 1.2

router = Router(name=__name__)

user_states: Dict[int, str] = {}
user_last_messages: Dict[int, Tuple[int, int]] = {}


@asynccontextmanager
async def typing_context(chat_id: int, bot: Bot, interval: float = 4.0):
    """Показывать индикатор 'печатает…' пока запрос обрабатывается."""
    stop_typing = asyncio.Event()

    async def typing_worker():
        while not stop_typing.is_set():
            try:
                await bot.send_chat_action(chat_id, "typing")
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception:
                break

    typing_task = asyncio.create_task(typing_worker())
    try:
        yield
    finally:
        stop_typing.set()
        typing_task.cancel()
        with suppress(asyncio.CancelledError):
            await typing_task


def create_retry_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🔄 Повторить", callback_data="retry_request"))
    builder.add(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_retry"))
    return builder.as_markup()


async def send_message_safe(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    reply_to_message_id: Optional[int] = None,
) -> Optional[Message]:
    try:
        if len(text) > 4096:
            chunks = [text[i : i + 4096] for i in range(0, len(text), 4096)]
            sent_msg = None
            for i, chunk in enumerate(chunks):
                markup = reply_markup if i == len(chunks) - 1 else None
                sent_msg = await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    reply_markup=markup,
                    reply_to_message_id=reply_to_message_id if i == 0 else None,
                )
            return sent_msg
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            reply_to_message_id=reply_to_message_id,
        )
    except TelegramBadRequest:
        try:
            return await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                reply_to_message_id=reply_to_message_id,
                parse_mode=None,
            )
        except Exception:
            return None
    except Exception:
        return None


def _ensure_connected(user_id: int) -> bool:
    """Подключить юзера к агенту если ещё не подключён и стоит AUTO_CONNECT_ON_START."""
    if session_store.is_connected(user_id):
        user_states[user_id] = "connected"
        return True
    cfg = get_config()
    if not cfg.AUTO_CONNECT_ON_START or not cfg.AGENT_API_URL:
        return False
    session_store.connect_agent(user_id, cfg.AGENT_API_URL)
    user_states[user_id] = "connected"
    return True


def _compose_stream_view(status: str, text: str) -> str:
    """Собрать тело live-сообщения: статус-строка сверху, накопленный ответ снизу."""
    parts = []
    if status:
        parts.append(status)
    if text:
        parts.append(text)
    if not parts:
        return "🤔 Думаю…"
    body = "\n\n".join(parts)
    # Telegram режет на 4096 символов — оставляем место под статус
    if len(body) > 4000:
        body = body[:4000] + "…"
    return body


async def _safe_edit(bot: Bot, chat_id: int, message_id: int, text: str) -> None:
    """Edit, который проглатывает 'not modified' и проблемы парсинга."""
    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text, parse_mode=None
        )
    except TelegramBadRequest as e:
        # message is not modified / message can't be edited / etc.
        if "not modified" in str(e).lower():
            return
        # не критично — следующий тик перезапишет
        return
    except Exception:
        return


async def _run_agent_query(bot: Bot, user_id: int, message: Message, query: str) -> None:
    """Подключиться к агенту, отправить запрос через streaming и live-обновлять ответ."""
    if not _ensure_connected(user_id):
        await send_message_safe(
            bot,
            user_id,
            "❌ Нет подключения к агенту. Включите AUTO_CONNECT_ON_START или используйте /start.",
            reply_to_message_id=message.message_id,
        )
        return

    agent = session_store.get_agent(user_id)
    if not agent:
        await send_message_safe(bot, user_id, "❌ Не удалось получить агента.")
        return

    async def process_request():
        placeholder: Optional[Message] = None
        try:
            placeholder = await send_message_safe(
                bot, user_id, "🤔 Думаю…", reply_to_message_id=message.message_id
            )

            status_line = ""
            answer_text = ""
            last_edit_ts = 0.0
            last_rendered = "🤔 Думаю…"

            async for event in agent.stream_message(query):
                if asyncio.current_task() and asyncio.current_task().cancelled():
                    return

                kind = event["type"]
                content = event.get("content", "")

                if kind == "status":
                    status_line = content
                elif kind == "text":
                    answer_text = content
                elif kind == "done":
                    final_text = content or answer_text or "✅ Готово, но ответ пустой."
                    if placeholder:
                        await _safe_edit(bot, user_id, placeholder.message_id, final_text)
                    else:
                        await send_message_safe(
                            bot, user_id, final_text, reply_to_message_id=message.message_id
                        )
                    return
                elif kind == "error":
                    err_text = f"❌ {content}"
                    if placeholder:
                        await _safe_edit(bot, user_id, placeholder.message_id, err_text)
                        # Прицепим клавиатуру отдельным сообщением
                        await send_message_safe(
                            bot,
                            user_id,
                            "Хотите повторить?",
                            reply_markup=create_retry_keyboard(),
                        )
                    else:
                        await send_message_safe(
                            bot,
                            user_id,
                            err_text,
                            reply_markup=create_retry_keyboard(),
                            reply_to_message_id=message.message_id,
                        )
                    return

                # Дросселированный edit на промежуточные события
                now = time.monotonic()
                if placeholder and (now - last_edit_ts) >= STREAM_EDIT_INTERVAL:
                    rendered = _compose_stream_view(status_line, answer_text)
                    if rendered != last_rendered:
                        await _safe_edit(bot, user_id, placeholder.message_id, rendered)
                        last_rendered = rendered
                        last_edit_ts = now

        except asyncio.CancelledError:
            pass
        except Exception as e:
            if placeholder:
                await _safe_edit(
                    bot, user_id, placeholder.message_id, f"❌ Ошибка: {str(e)}"
                )
            else:
                await send_message_safe(
                    bot,
                    user_id,
                    f"❌ Ошибка: {str(e)}",
                    reply_markup=create_retry_keyboard(),
                    reply_to_message_id=message.message_id,
                )

    task = asyncio.create_task(process_request())
    request_manager.add_request(user_id, task)


# ===== Команды =====


@router.message(CommandStart())
async def cmd_start(message: Message):
    if not message.from_user or not message.bot:
        return

    user_id = message.from_user.id
    connected = _ensure_connected(user_id)

    if connected:
        welcome_text = (
            "👋 Привет! Я Meeting Assistant.\n\n"
            "Уже подключён к агенту — пишите любой вопрос свободным текстом, или используйте команды:\n\n"
            "• /upcoming [N] — встречи на N дней вперёд\n"
            "• /summary <conference_id> — саммари созвона\n"
            "• /search <запрос> — поиск по транскрипциям\n"
            "• /help — справка"
        )
        await send_message_safe(message.bot, user_id, welcome_text, kb.disconnect_menu)
    else:
        user_states[user_id] = "main_menu"
        welcome_text = (
            "👋 Добро пожаловать в Meeting Assistant!\n\n"
            "Я помогу с созвонами, календарём и поиском по транскрипциям.\n"
            "Чтобы начать — подключитесь к агенту:"
        )
        await send_message_safe(message.bot, user_id, welcome_text, kb.main_menu)


@router.message(Command("help"))
async def cmd_help(message: Message):
    if not message.from_user or not message.bot:
        return
    help_text = (
        "🆘 Команды:\n\n"
        "• /start — приветствие и подключение\n"
        "• /upcoming [N] — предстоящие встречи на N дней (по умолчанию 7)\n"
        "• /summary <conference_id> — саммари созвона по ID\n"
        "• /search <запрос> — поиск по транскрипциям через RAG\n\n"
        "Кроме команд, агент понимает естественный язык:\n"
        "  «Создай встречу на завтра в 15:00»\n"
        "  «Подключись к https://meet.google.com/xxx»\n"
        "  «О чём говорили на последней встрече?»"
    )
    await send_message_safe(message.bot, message.from_user.id, help_text)


@router.message(Command("upcoming"))
async def cmd_upcoming(message: Message):
    if not message.from_user or not message.bot or not message.text:
        return
    parts = message.text.strip().split(maxsplit=1)
    days = 7
    if len(parts) > 1 and parts[1].isdigit():
        days = max(1, min(int(parts[1]), 30))
    query = f"Покажи предстоящие встречи на {days} дней вперёд (используй get_upcoming_events)."
    await _run_agent_query(message.bot, message.from_user.id, message, query)


@router.message(Command("summary"))
async def cmd_summary(message: Message):
    if not message.from_user or not message.bot or not message.text:
        return
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await send_message_safe(
            message.bot,
            message.from_user.id,
            "Использование: /summary <conference_id>\nПример: /summary 34faff15-20a3-4dee-b212-3c0a3604e239",
        )
        return
    conference_id = parts[1].strip()
    query = (
        f"Получи транскрипцию созвона {conference_id} через get_transcription "
        f"и составь короткое саммари (3-5 пунктов): ключевые решения, задачи, дедлайны."
    )
    await _run_agent_query(message.bot, message.from_user.id, message, query)


@router.message(Command("search"))
async def cmd_search(message: Message):
    if not message.from_user or not message.bot or not message.text:
        return
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await send_message_safe(
            message.bot,
            message.from_user.id,
            "Использование: /search <запрос>\nПример: /search обсуждение бюджета",
        )
        return
    query_text = parts[1].strip()
    query = (
        f"Выполни поиск по базе знаний через search_knowledge_base с запросом: «{query_text}». "
        f"Верни 3-5 наиболее релевантных фрагментов с указанием встречи."
    )
    await _run_agent_query(message.bot, message.from_user.id, message, query)


# ===== Callback-кнопки =====


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        return
    user_id = callback.from_user.id
    user_states[user_id] = "main_menu"
    await callback.message.edit_text("Главное меню:", reply_markup=kb.main_menu)
    await callback.answer()


@router.callback_query(F.data == "help")
async def show_help(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        return
    user_states[callback.from_user.id] = "help_menu"
    help_text = (
        "🆘 Что я умею:\n\n"
        "📅 Создание встреч: «Создай встречу на завтра в 14:00 на час»\n"
        "🎙 Запись созвонов: «Подключись к https://meet.google.com/xxx»\n"
        "🔍 Поиск по встречам: «О чём говорили на прошлой встрече?»\n"
        "📋 Списки: «Покажи последние созвоны»\n\n"
        "Быстрые команды: /upcoming, /summary, /search"
    )
    await callback.message.edit_text(help_text, reply_markup=kb.help_menu)
    await callback.answer()


@router.callback_query(F.data == "start_work")
async def start_work(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        return
    user_states[callback.from_user.id] = "start_work_menu"
    await callback.message.edit_text(
        "Начало работы с агентом:", reply_markup=kb.start_work_menu
    )
    await callback.answer()


@router.callback_query(F.data == "connect_to_agent")
async def connect_to_agent(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        return
    user_id = callback.from_user.id
    cfg = get_config()
    try:
        agent_url = cfg.AGENT_API_URL
        if not agent_url:
            raise ValueError("AGENT_API_URL not configured")
        session_store.connect_agent(user_id, agent_url)
        user_states[user_id] = "connected"
        await callback.message.edit_text(
            f"✅ Подключено к агенту\n• URL: {agent_url}\n\nТеперь можно писать запросы.",
            reply_markup=kb.disconnect_menu,
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка подключения: {str(e)}", reply_markup=kb.connect_cancel_menu
        )
    await callback.answer()


@router.callback_query(F.data == "cancel_connect")
async def cancel_connect(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        return
    user_states[callback.from_user.id] = "start_work_menu"
    await callback.message.edit_text(
        "Подключение отменено.", reply_markup=kb.start_work_menu
    )
    await callback.answer()


@router.callback_query(F.data == "disconnect")
async def disconnect_agent(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        return
    user_id = callback.from_user.id
    session_store.disconnect_agent(user_id)
    user_states[user_id] = "main_menu"
    await callback.message.edit_text(
        "✅ Вы отключены от агента", reply_markup=kb.main_menu
    )
    await callback.answer()


@router.callback_query(F.data == "retry_request")
async def retry_request(callback: CallbackQuery):
    await callback.answer("Функция повтора в разработке")


@router.callback_query(F.data == "cancel_retry")
async def cancel_retry(callback: CallbackQuery):
    if not callback.from_user or not callback.message:
        return
    await callback.message.edit_text("❌ Отменено", reply_markup=kb.main_menu)
    await callback.answer()


# ===== Свободный текст =====


@router.message()
async def handle_message(message: Message):
    if not message.from_user or not message.text or not message.bot:
        return
    user_id = message.from_user.id
    await _run_agent_query(message.bot, user_id, message, message.text)


@router.edited_message()
async def handle_edited_message(message: Message):
    if not message.from_user or not message.text or not config.HANDLE_MESSAGE_EDITS:
        return
    user_id = message.from_user.id
    if user_states.get(user_id) == "connected":
        request_manager.cancel_request(user_id)
        await handle_message(message)
