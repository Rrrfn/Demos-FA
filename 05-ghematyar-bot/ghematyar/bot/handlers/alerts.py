# -*- coding: utf-8 -*-
"""هندلرهای هشدار: ساخت مرحله‌به‌مرحله، پارس متن آزاد و مدیریت."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ...core import assets as asset_registry
from ...core.errors import AlertLimitReached, AlertNotFound, DuplicateAlert
from ...core.formatting import fa_num, to_float
from ...storage import AlertDirection
from ...services import Services
from .. import keyboards, parsing, texts

log = logging.getLogger("ghematyar.handlers.alerts")


class AlertFlow(StatesGroup):
    """مراحل ساخت هشدار."""

    choosing_asset = State()
    choosing_direction = State()
    waiting_target = State()


# ------------------------------------------------------------------- helpers
def _unit_word(slug: str) -> str:
    asset = asset_registry.ASSETS.get(slug)
    return "دلار" if asset and asset.unit == "usd" else "تومان"


async def _create_and_report(
    message: Message, services: Services, slug: str, direction: AlertDirection, target: float
) -> None:
    """ساخت هشدار و گزارش خطاهای سیاست به‌صورت پیام روشن."""
    try:
        alert = services.alerts.create(message.from_user.id, slug, direction, target)
    except DuplicateAlert as exc:
        await message.answer(
            f"🔁 این هشدار از قبل ثبت شده است (#{exc.alert_id}).\n"
            "برای تغییر مقدار، ابتدا همان هشدار را حذف یا ویرایش کنید.",
            reply_markup=keyboards.alerts_keyboard(services.alerts.list(message.from_user.id)),
        )
        return
    except AlertLimitReached as exc:
        await message.answer(
            f"⛔ به سقف {fa_num(exc.limit)} هشدار فعال رسیده‌اید.\n"
            "برای ساخت هشدار تازه، یکی از هشدارهای موجود را حذف کنید.",
            reply_markup=keyboards.alerts_keyboard(services.alerts.list(message.from_user.id)),
        )
        return
    await message.answer(
        texts.render_alert_created(alert),
        reply_markup=keyboards.alerts_keyboard(services.alerts.list(message.from_user.id)),
    )


# ------------------------------------------------------------------ commands
async def cmd_alert(
    message: Message, services: Services, state: FSMContext, command: CommandObject
) -> None:
    """ساخت هشدار — با آرگومان، پارس فوری؛ بدون آن، انتخاب مرحله‌به‌مرحله."""
    args = (command.args or "").strip()
    if args:
        expression = parsing.parse_alert_expression(args)
        if expression.complete:
            await _create_and_report(
                message, services, expression.slug, expression.direction, expression.target
            )
            await state.clear()
            return
        # بخشی از اطلاعات را از متن گرفتیم؛ بقیه را می‌پرسیم
        if expression.slug:
            await state.update_data(slug=expression.slug)
            if expression.direction and expression.target:
                await _create_and_report(
                    message, services, expression.slug, expression.direction, expression.target
                )
                await state.clear()
                return
            if expression.direction:
                await state.update_data(direction=expression.direction.value)
                await message.answer(
                    f"{asset_registry.ASSETS[expression.slug].emoji} "
                    f"<b>{texts.title_of(expression.slug)}</b>\n"
                    f"جهت: {expression.direction.label}\n\n"
                    "چه عددی را آستانه بگذارم؟ مثلاً <code>۲۵۰۰۰۰۰</code>",
                )
                await state.set_state(AlertFlow.waiting_target)
                return

    alerts = services.alerts.list(message.from_user.id)
    if alerts:
        await message.answer(
            texts.render_alerts(alerts, limit=services.config.alerts.max_per_user),
            reply_markup=keyboards.alerts_keyboard(alerts),
        )
    else:
        await message.answer(
            "🔔 برای ساخت هشدار، ابتدا قلم را انتخاب کنید:\n\n"
            "یا مستقیم بنویسید: «دلار بالای ۲۵۰۰۰۰»",
            reply_markup=keyboards.assets_keyboard(
                list(asset_registry.FEATURED), action="alertpick"
            ),
        )
        await state.set_state(AlertFlow.choosing_asset)


async def cmd_alerts(message: Message, services: Services) -> None:
    """فهرست و مدیریت هشدارها."""
    alerts = services.alerts.list(message.from_user.id)
    await message.answer(
        texts.render_alerts(alerts, limit=services.config.alerts.max_per_user),
        reply_markup=keyboards.alerts_keyboard(alerts),
    )


async def cmd_events(message: Message, services: Services) -> None:
    """گزارش رخدادها — پاسخ به «چرا اعلان نگرفتم؟»."""
    rows = services.alerts.recent_events(message.from_user.id, limit=15)
    used, limit = services.alerts.usage(message.from_user.id)
    await message.answer(
        texts.render_alert_events(rows)
        + f"\n\n<b>ظرفیت:</b> {fa_num(used)} از {fa_num(limit)} هشدار فعال",
        reply_markup=keyboards.back_to_menu(),
    )


# --------------------------------------------------------------- FSM: target
async def on_target(message: Message, services: Services, state: FSMContext) -> None:
    """دریافت آستانه (عدد) برای هشدار نیمه‌تمام."""
    text = (message.text or "").strip()
    if text.startswith("/"):
        await state.clear()
        await message.answer("لغو شد. برای شروع دوباره /alert را بزنید.")
        return
    data = await state.get_data()
    slug = data.get("slug")
    direction_value = data.get("direction")
    if not slug or not asset_registry.exists(slug) or not direction_value:
        await state.clear()
        await message.answer("اطلاعات هشدار کامل نبود؛ از /alert دوباره شروع کنید.")
        return

    target = to_float(text)
    if target <= 0:
        await message.answer(
            "عدد معتبر نیست. یک مقدار عددی بفرستید؛ مثلاً <code>۲۵۰۰۰۰۰</code> "
            "یا <code>۲.۵ میلیارد</code>."
        )
        return
    await _create_and_report(
        message, services, slug, AlertDirection(direction_value), target
    )
    await state.clear()


# ---------------------------------------------------------------- callbacks
async def cb_alerts(callback: CallbackQuery, services: Services) -> None:
    alerts = services.alerts.list(callback.from_user.id)
    text = texts.render_alerts(alerts, limit=services.config.alerts.max_per_user)
    if callback.message is not None:
        try:
            await callback.message.edit_text(text, reply_markup=keyboards.alerts_keyboard(alerts))
        except Exception:  # noqa: BLE001
            await callback.message.answer(text, reply_markup=keyboards.alerts_keyboard(alerts))
    await callback.answer()


async def cb_events(callback: CallbackQuery, services: Services) -> None:
    rows = services.alerts.recent_events(callback.from_user.id, limit=12)
    text = texts.render_alert_events(rows)
    if callback.message is not None:
        try:
            await callback.message.edit_text(text, reply_markup=keyboards.back_to_menu())
        except Exception:  # noqa: BLE001
            await callback.message.answer(text, reply_markup=keyboards.back_to_menu())
    await callback.answer()


async def cb_alert_new(callback: CallbackQuery, services: Services, state: FSMContext) -> None:
    await state.set_state(AlertFlow.choosing_asset)
    if callback.message is not None:
        await callback.message.answer(
            "قلم مورد نظر را انتخاب کنید:",
            reply_markup=keyboards.assets_keyboard(
                list(asset_registry.FEATURED), action="alertpick"
            ),
        )
    await callback.answer()


async def cb_alert_from_price(callback: CallbackQuery, state: FSMContext) -> None:
    slug = (callback.data or "").split(":", 1)[1]
    if not asset_registry.exists(slug):
        await callback.answer("قلم ناشناخته", show_alert=True)
        return
    await state.update_data(slug=slug)
    await state.set_state(AlertFlow.choosing_direction)
    if callback.message is not None:
        await callback.message.answer(
            f"{texts.emoji_of(slug)} <b>{texts.title_of(slug)}</b>\nشرط را انتخاب کنید:",
            reply_markup=keyboards.alert_direction_keyboard(slug),
        )
    await callback.answer()


async def cb_alert_pick(callback: CallbackQuery, state: FSMContext) -> None:
    slug = (callback.data or "").split(":", 1)[1]
    if not asset_registry.exists(slug):
        await callback.answer("قلم ناشناخته", show_alert=True)
        return
    await state.update_data(slug=slug)
    await state.set_state(AlertFlow.choosing_direction)
    if callback.message is not None:
        await callback.message.answer(
            f"{texts.emoji_of(slug)} <b>{texts.title_of(slug)}</b>\nشرط را انتخاب کنید:",
            reply_markup=keyboards.alert_direction_keyboard(slug),
        )
    await callback.answer()


async def cb_alert_direction(callback: CallbackQuery, state: FSMContext) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer("درخواست نامعتبر", show_alert=True)
        return
    _, direction_value, slug = parts
    try:
        direction = AlertDirection(direction_value)
    except ValueError:
        await callback.answer("جهت نامعتبر", show_alert=True)
        return
    await state.update_data(slug=slug, direction=direction.value)
    await state.set_state(AlertFlow.waiting_target)
    if callback.message is not None:
        await callback.message.answer(
            f"عدد آستانه را بفرستید (مثلاً <code>۲۵۰۰۰۰۰</code>) — "
            f"قیمت {direction.label} چه مقداری خبر بدهم؟"
        )
    await callback.answer()


async def cb_alert_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is not None:
        await callback.message.answer("لغو شد.", reply_markup=keyboards.main_menu())
    await callback.answer()


async def cb_alert_info(callback: CallbackQuery, services: Services) -> None:
    try:
        alert_id = int((callback.data or "").split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("شناسه نامعتبر", show_alert=True)
        return
    try:
        alert = services.alerts.get(callback.from_user.id, alert_id)
    except AlertNotFound:
        await callback.answer("این هشدار پیدا نشد", show_alert=True)
        return
    last_price = (
        f"آخرین قیمت دیده‌شده: {fa_num(alert.last_price)} {_unit_word(alert.slug)}"
        if alert.last_price
        else "هنوز قیمتی برای این هشدار ثبت نشده است."
    )
    text = (
        f"🔔 <b>هشدار #{alert.id}</b>\n\n"
        f"{texts.emoji_of(alert.slug)} <b>{texts.title_of(alert.slug)}</b>\n"
        f"شرط: {alert.direction.label} {fa_num(alert.target)} {_unit_word(alert.slug)}\n"
        f"وضعیت: {alert.status.label}\n"
        f"حالت: {'یک‌بار مصرف' if alert.one_shot else 'تکرارشونده'}\n"
        f"تعداد اجرا: {fa_num(alert.triggered_count)}\n"
        f"{last_price}"
    )
    if callback.message is not None:
        await callback.message.answer(text, reply_markup=keyboards.alerts_keyboard(
            services.alerts.list(callback.from_user.id)
        ))
    await callback.answer()


async def cb_alert_toggle(callback: CallbackQuery, services: Services) -> None:
    try:
        alert_id = int((callback.data or "").split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("شناسه نامعتبر", show_alert=True)
        return
    try:
        alert = services.alerts.toggle(callback.from_user.id, alert_id)
    except AlertNotFound:
        await callback.answer("این هشدار پیدا نشد", show_alert=True)
        return
    alerts = services.alerts.list(callback.from_user.id)
    if callback.message is not None:
        try:
            await callback.message.edit_text(
                texts.render_alerts(alerts, limit=services.config.alerts.max_per_user),
                reply_markup=keyboards.alerts_keyboard(alerts),
            )
        except Exception:  # noqa: BLE001
            pass
    await callback.answer(f"وضعیت: {alert.status.label}")


async def cb_alert_delete(callback: CallbackQuery, services: Services) -> None:
    try:
        alert_id = int((callback.data or "").split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("شناسه نامعتبر", show_alert=True)
        return
    try:
        services.alerts.remove(callback.from_user.id, alert_id)
    except AlertNotFound:
        await callback.answer("این هشدار پیدا نشد", show_alert=True)
        return
    alerts = services.alerts.list(callback.from_user.id)
    if callback.message is not None:
        try:
            await callback.message.edit_text(
                texts.render_alerts(alerts, limit=services.config.alerts.max_per_user),
                reply_markup=keyboards.alerts_keyboard(alerts),
            )
        except Exception:  # noqa: BLE001
            pass
    await callback.answer("حذف شد")


def build_router() -> Router:
    """ساخت router تازهٔ هشدارها (دستورها، FSM و callbackها)."""
    router = Router(name="alerts")
    router.message.register(cmd_alert, Command("alert"))
    router.message.register(cmd_alerts, Command("alerts"))
    router.message.register(cmd_events, Command("events"))
    router.message.register(on_target, AlertFlow.waiting_target, F.text)
    router.callback_query.register(cb_alerts, F.data == "nav:alerts")
    router.callback_query.register(cb_events, F.data == "nav:events")
    router.callback_query.register(cb_alert_new, F.data == "nav:alertnew")
    router.callback_query.register(cb_alert_from_price, F.data.startswith("alertnew:"))
    router.callback_query.register(cb_alert_pick, F.data.startswith("alertpick:"))
    router.callback_query.register(cb_alert_direction, F.data.startswith("alertdir:"))
    router.callback_query.register(cb_alert_cancel, F.data == "alertcancel")
    router.callback_query.register(cb_alert_info, F.data.startswith("alertinfo:"))
    router.callback_query.register(cb_alert_toggle, F.data.startswith("alerttoggle:"))
    router.callback_query.register(cb_alert_delete, F.data.startswith("alertdel:"))
    return router


__all__ = ["build_router", "AlertFlow", "on_target"]
