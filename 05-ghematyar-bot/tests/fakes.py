# -*- coding: utf-8 -*-
"""دوقلوهای تست.

هدف: آزمودن رفتار واقعی بدون هیچ تماس شبکه‌ای.

* ``FakeSession`` قرارداد نشست تلگرام را پیاده می‌کند و همهٔ درخواست‌های
  خروجی را ثبت می‌کند، پس می‌توان دقیقاً بررسی کرد ربات چه پیامی می‌فرستد.
* ``ScriptedProvider`` یک ارائه‌دهندهٔ داده با پاسخ‌های از پیش تعیین‌شده
  است تا سناریوهای «منبع خطا می‌دهد»، «پاسخ نامعتبر است» و «fallback»
  قابل بازتولید باشند.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncGenerator, Sequence

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import (
    AnswerCallbackQuery,
    DeleteWebhook,
    EditMessageText,
    GetMe,
    SendMessage,
    SendPhoto,
    SetWebhook,
    TelegramMethod,
)
from aiogram.types import Chat, Message, Update, User

from ghematyar.core.errors import ProviderError
from ghematyar.core.models import Quote
from ghematyar.providers.base import BaseProvider, HttpClient

TEST_BOT_USER = User(id=99, is_bot=True, first_name="GhematyarTest", username="ghematyar_test_bot")


class FakeSession(BaseSession):
    """نشست تلگرام قلابی — همهٔ متدها را ثبت و پاسخ کاذب برمی‌گرداند."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod[Any]] = []
        self._message_id = 1000

    @property
    def sent_texts(self) -> list[str]:
        """متن پیام‌هایی که ربات فرستاده است."""
        return [str(m.text) for m in self.requests if isinstance(m, SendMessage)]

    @property
    def sent_captions(self) -> list[str]:
        """کپشن عکس‌هایی که ربات فرستاده است."""
        return [str(m.caption) for m in self.requests if isinstance(m, SendPhoto)]

    @property
    def edited_texts(self) -> list[str]:
        return [str(m.text) for m in self.requests if isinstance(m, EditMessageText)]

    def last_send(self) -> SendMessage | None:
        for method in reversed(self.requests):
            if isinstance(method, SendMessage):
                return method
        return None

    def clear(self) -> None:
        self.requests.clear()

    async def close(self) -> None:  # pragma: no cover - nothing to release
        return None

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        if False:  # سازگاری با امضای مولد ناهمگام
            yield b""

    async def make_request(
        self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None
    ) -> Any:
        self.requests.append(method)
        if isinstance(method, GetMe):
            return TEST_BOT_USER
        if isinstance(method, (SetWebhook, DeleteWebhook, AnswerCallbackQuery)):
            return True
        if isinstance(method, (SendMessage, EditMessageText, SendPhoto)):
            self._message_id += 1
            chat_id = getattr(method, "chat_id", 1)
            return Message(
                message_id=self._message_id,
                date=int(time.time()),
                chat=Chat(id=int(chat_id), type="private"),
                from_user=TEST_BOT_USER,
                text=getattr(method, "text", None) or getattr(method, "caption", None),
            )
        return True


def make_bot(session: FakeSession | None = None) -> Bot:
    """ربات متصل به نشست قلابی — هیچ شبکه‌ای در کار نیست."""
    return Bot(
        token="123456:TEST-TOKEN",
        session=session or FakeSession(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def make_message_update(text: str = "", user_id: int = 777, message_id: int = 1) -> Update:
    """ساخت آپدیت متنی برای feed_update."""
    return Update(
        update_id=message_id,
        message=Message(
            message_id=message_id,
            date=int(time.time()),
            chat=Chat(id=user_id, type="private"),
            from_user=User(id=user_id, is_bot=False, first_name="Tester"),
            text=text,
        ),
    )


def make_callback_update(data: str, user_id: int = 777, message_id: int = 5) -> Update:
    """ساخت آپدیت کلیک روی دکمه."""
    from aiogram.types import CallbackQuery

    message = Message(
        message_id=message_id,
        date=int(time.time()),
        chat=Chat(id=user_id, type="private"),
        from_user=TEST_BOT_USER,
        text="قبلی",
    )
    return Update(
        update_id=message_id,
        callback_query=CallbackQuery(
            id=f"cb-{message_id}",
            from_user=User(id=user_id, is_bot=False, first_name="Tester"),
            chat_instance="ci",
            data=data,
            message=message,
        ),
    )


class ScriptedProvider(BaseProvider):
    """ارائه‌دهندهٔ داده با پاسخ از پیش تعیین‌شده (برای سناریوهای خطا).

    ``script`` می‌تواند یکی از این‌ها باشد:

    * dict[str, Quote]  → پاسخ موفق
    * Exception         → برای پرتاب شدن (شبیه‌سازی خطای شبکه/منبع)
    * list              → پاسخ‌های متوالی برای فراخوانی‌های پشت‌سرهم
    """

    def __init__(self, name: str, script: Any, config) -> None:
        client = HttpClient(config)
        super().__init__(client, config)
        self.name = name
        self.script = script if isinstance(script, list) else [script]
        self.calls: list[list[str]] = []

    async def _fetch(self, slugs: Sequence[str] | None = None) -> dict[str, Quote]:
        self.calls.append(list(slugs or []))
        response = self.script[min(len(self.calls) - 1, len(self.script) - 1)]
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return response(list(slugs or []))
        return dict(response)


async def no_sleep(*_args, **_kwargs) -> None:
    """جایگزین asyncio.sleep در تست‌های زمان‌دار."""
    await asyncio.sleep(0)


# ------------------------------------------------------------------ HTTP fakes
class FakeHttpResponse:
    """پاسخ aiohttp قلابی."""

    def __init__(self, status: int, payload: Any = None, text: str = "", headers: dict | None = None,
                 *, invalid_json: bool = False) -> None:
        self.status = status
        self._payload = payload
        self._text = text
        self.headers = headers or {}
        self._invalid_json = invalid_json

    async def __aenter__(self) -> "FakeHttpResponse":
        return self

    async def __aexit__(self, *_exc) -> bool:
        return False

    async def json(self, content_type: Any = None) -> Any:
        if self._invalid_json:
            raise ValueError("not json")
        return self._payload

    async def text(self) -> str:
        return self._text


def timeout_error() -> Exception:
    """شبیه‌سازی timeout در aiohttp."""
    return asyncio.TimeoutError()


class FakeAiohttpSession:
    """نشست aiohttp قلابی با پاسخ‌های پشت‌سرهم.

    هر بار ``get`` پاسخ بعدی لیست را برمی‌گرداند؛ اگر پاسخ استثنا باشد،
    همان بالا می‌رود (براي شبیه‌سازی خطای شبکه).
    """

    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.urls: list[str] = []
        self.closed = False

    def get(self, url: str) -> Any:
        self.urls.append(url)
        item = self.responses[min(len(self.urls) - 1, len(self.responses) - 1)]
        if isinstance(item, Exception):
            class _Raiser:
                def __init__(self, exc: Exception) -> None:
                    self.exc = exc

                async def __aenter__(self):
                    raise self.exc

                async def __aexit__(self, *_exc) -> bool:
                    return False

            return _Raiser(item)
        return item

    async def close(self) -> None:
        self.closed = True


__all__ = [
    "FakeAiohttpSession",
    "FakeHttpResponse",
    "FakeSession",
    "ScriptedProvider",
    "make_bot",
    "make_callback_update",
    "make_message_update",
    "no_sleep",
]
