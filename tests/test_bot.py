from collections.abc import Callable, Coroutine
from types import SimpleNamespace
from typing import Any

import pytest
from telebot.async_telebot import AsyncTeleBot

from paperless_genie import bot as bot_module
from paperless_genie.config import Config


class StubBot:
    """Records every method call instead of touching the Telegram API.

    Any attribute access returns an async recorder, so a handler can call
    reply_to / send_message / edit_message_text / etc. and we can assert on
    what (if anything) it tried to do.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> Callable[..., Coroutine[Any, Any, Any]]:
        async def recorder(*args: object, **kwargs: object) -> SimpleNamespace:
            self.calls.append(name)
            # Emulate the message object reply_to/send_message return.
            return SimpleNamespace(chat=SimpleNamespace(id=1), message_id=1)

        return recorder


def _message(user_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        chat=SimpleNamespace(id=1),
        text="hello",
        document=None,
        photo=None,
        caption=None,
    )


_MESSAGE_HANDLERS = [
    bot_module.send_welcome,
    bot_module.handle_clear,
    bot_module.handle_get,
    bot_module.handle_document,
    bot_module.handle_photo,
    bot_module.handle_text_query,
]


@pytest.mark.parametrize("handler", _MESSAGE_HANDLERS)
async def test_message_handlers_ignore_unauthorized_user(
    handler: Callable[..., Coroutine[Any, Any, None]], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Empty token map → nobody is authorized.
    monkeypatch.setattr(Config, "USER_TOKENS", {})
    stub = StubBot()

    await handler(_message(user_id=999), stub)

    # An unauthorized user must get complete silence — no API calls at all.
    assert stub.calls == []


async def test_message_handler_serves_authorized_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "USER_TOKENS", {42: "token"})
    stub = StubBot()

    await bot_module.send_welcome(_message(user_id=42), stub)

    # The welcome path only calls reply_to — no network, safe to assert directly.
    assert stub.calls == ["reply_to"]


async def test_callback_handler_denies_unauthorized_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "USER_TOKENS", {})
    stub = StubBot()
    call = SimpleNamespace(
        from_user=SimpleNamespace(id=999),
        id="cb1",
        data="get_doc:42",
        message=SimpleNamespace(chat=SimpleNamespace(id=1)),
    )

    await bot_module.handle_doc_button(call, stub)

    # The callback answers with a denial and does nothing else.
    assert stub.calls == ["answer_callback_query"]


def test_create_bot_registers_all_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "TELEGRAM_BOT_TOKEN", "123456:test-token")

    bot = bot_module.create_bot(Config)

    assert isinstance(bot, AsyncTeleBot)
    assert len(bot.message_handlers) == len(_MESSAGE_HANDLERS)
    assert len(bot.callback_query_handlers) == 1


def test_extract_doc_ids_deduplicates_preserving_order() -> None:
    text = "First [#42] then [#7] then [#42] again and [#7]."
    assert bot_module._extract_doc_ids(text) == [42, 7]


def test_extract_doc_ids_returns_empty_when_no_markers() -> None:
    assert bot_module._extract_doc_ids("no markers here") == []


def test_chunk_text_returns_single_chunk_at_or_under_limit() -> None:
    assert bot_module._chunk_text("", limit=10) == [""]
    assert bot_module._chunk_text("exactly10!", limit=10) == ["exactly10!"]


def test_chunk_text_splits_past_the_limit() -> None:
    assert bot_module._chunk_text("abcdefghijk", limit=10) == ["abcdefghij", "k"]
    assert bot_module._chunk_text("a" * 25, limit=10) == ["a" * 10, "a" * 10, "a" * 5]


def test_build_doc_keyboard_none_when_empty() -> None:
    assert bot_module._build_doc_keyboard([]) is None


def test_build_doc_keyboard_has_one_button_per_id() -> None:
    keyboard = bot_module._build_doc_keyboard([42, 7])
    assert keyboard is not None
    buttons = [button for row in keyboard.keyboard for button in row]
    assert [b.callback_data for b in buttons] == ["get_doc:42", "get_doc:7"]
