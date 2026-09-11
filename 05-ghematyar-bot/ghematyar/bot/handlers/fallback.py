# -*- coding: utf-8 -*-
"""آخرین مسیر: متن آزاد کاربر.

منطق: اگر متن شرط هشدار را کامل داشته باشد («دلار بالای ۲۵۰۰۰۰») هشدار
می‌سازیم؛ اگر قلم و جهت را داشته ولی آستانه را نداشته باشد («دلار بالای»)
عدد را می‌پرسیم؛ اگر نام یک قلم باشد قیمتش را می‌دهیم؛ و در غیر این صورت
راهنما. هیچ حالتی به پاسخ ساختگی ختم نمی‌شود.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from ...core import assets as asset_registry
from ...services import Services
from .. import keyboards, parsing, texts

log = logging.getLogger("ghematyar.handlers.fallback")


async def on_text(message: Message, services: Services, state: FSMContext) -> None:
    """تفسیر متن آزاد."""
    text = (message.text or "").strip()
    if not text:
        return

    expression = parsing.parse_alert_expression(text)
    if expression.slug and expression.direction:
        from .alerts import AlertFlow, _create_and_report

        if expression.target:
            # قصد کاربر ساخت هشدار است و همهٔ اجزا را دارد
            await _create_and_report(
                message, services, expression.slug, expression.direction, expression.target
            )
            await state.clear()
            return

        # نیت کاربر ساخت هشدار است ولی آستانه را نگفته؛ به‌جای نادیده گرفتن
        # نیت او، همان جریان هشدار را ادامه می‌دهیم و عدد را می‌پرسیم.
        await state.update_data(slug=expression.slug, direction=expression.direction.value)
        await state.set_state(AlertFlow.waiting_target)
        await message.answer(
            f"🔔 هشدار برای {texts.emoji_of(expression.slug)} "
            f"<b>{texts.title_of(expression.slug)}</b>\n"
            f"جهت: {expression.direction.label}\n\n"
            "عدد آستانه را بفرستید؛ مثلاً <code>۲۵۰۰۰۰۰</code>"
        )
        return

    found = asset_registry.search(text)
    if found is not None:
        from .market import _send_quote

        await _send_quote(message, services, found.slug)
        return

    await message.answer(texts.HELP, reply_markup=keyboards.main_menu())


def build_router() -> Router:
    """ساخت router تازهٔ مسیر متن آزاد (باید آخرین router باشد)."""
    router = Router(name="fallback")
    router.message.register(on_text, F.text)
    return router


__all__ = ["build_router"]
