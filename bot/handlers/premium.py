import logging
from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    PreCheckoutQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    LabeledPrice
)
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from typing import Optional
from core.database.models import User
from core.database.repository import SubscriptionRepository, UserRepository
from services.payment.stars import TelegramStarsProvider

logger = logging.getLogger(__name__)

router = Router(name="premium")


def get_premium_keyboard(has_pro: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    if not has_pro:
        buttons.append([
            InlineKeyboardButton(text="⭐ Оформить PRO (150 Stars)", callback_data="buy_sub:pro")
        ])
        buttons.append([
            InlineKeyboardButton(text="🌟 Оформить TEAM (400 Stars)", callback_data="buy_sub:team")
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="🔄 Продлить PRO на 30 дней (150 Stars)", callback_data="buy_sub:pro")
        ])
    buttons.append([
        InlineKeyboardButton(text="📋 Мой трекер откликов", callback_data="open_tracker"),
        InlineKeyboardButton(text="🔙 Главное меню", callback_data="to_main_menu")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("premium"))
async def cmd_premium(message: Message, session: AsyncSession, user: Optional[User] = None) -> None:
    if user is None:
        user = await UserRepository.get_or_create_user(
            session=session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name
        )

    sub = await SubscriptionRepository.get_subscription(session, user.telegram_id)
    has_active = await SubscriptionRepository.has_active_subscription(session, user.telegram_id)

    status_str = "🆓 <b>Тариф: Базовый (Free)</b>"
    if has_active and sub:
        exp_date = sub.expires_at.strftime("%d.%m.%Y") if sub.expires_at else "бессрочно"
        status_str = f"⭐ <b>Тариф: {sub.plan.upper()} (активен до {exp_date})</b>"

    text = (
        f"💎 <b>Премиум-подписка JobScout</b>\n\n"
        f"Текущий статус: {status_str}\n\n"
        f"<b>Что даёт подписка PRO:</b>\n"
        f"• 🚀 <b>Все 9 источников</b> (HH, Хабр, ТрудВсем, SuperJob, Kwork, FL.ru, Freelance.ru, RemoteOK, Работа.ру)\n"
        f"• ✍️ <b>AI-сопроводительные письма</b> — идеальный отклик под требования конкретной вакансии в 1 клик\n"
        f"• 🔍 <b>AI Gap-анализ</b> — персональный разбор пробелов в навыках и план подготовки к собеседованию\n"
        f"• 📊 <b>Канбан-трекер откликов</b> — удобное ведение всех этапов (Отклик ➔ Скрининг ➔ Интервью ➔ Оффер)\n"
        f"• ⚡ <b>Мгновенные уведомления</b> о горячих вакансиях без задержек\n\n"
        f"Оплата в один клик через <b>Telegram Stars (XTR)</b> прямо в приложении!"
    )

    await message.answer(text, reply_markup=get_premium_keyboard(has_pro=has_active))


@router.callback_query(F.data.startswith("buy_sub:"))
async def on_buy_subscription(call: CallbackQuery, session: AsyncSession, user: Optional[User] = None) -> None:
    if user is None:
        user = await UserRepository.get_or_create_user(
            session=session,
            telegram_id=call.from_user.id,
            username=call.from_user.username,
            first_name=call.from_user.first_name
        )

    plan = call.data.split(":", 1)[1]
    provider = TelegramStarsProvider()
    payload_data = await provider.create_invoice_payload(user.telegram_id, plan)

    prices = [LabeledPrice(label=p["label"], amount=p["amount"]) for p in payload_data["prices"]]

    await call.message.answer_invoice(
        title=payload_data["title"],
        description=payload_data["description"],
        payload=payload_data["payload"],
        currency=payload_data["currency"],
        prices=prices,
        provider_token=payload_data["provider_token"],
        start_parameter=payload_data["start_parameter"]
    )
    await call.answer()


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    # Always accept Telegram Stars pre-checkout for legitimate subscriptions
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message, session: AsyncSession, user: Optional[User] = None) -> None:
    if user is None:
        user = await UserRepository.get_or_create_user(
            session=session,
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name
        )

    payment = message.successful_payment
    provider = TelegramStarsProvider()

    res = await provider.confirm_payment(
        session=session,
        user_id=user.telegram_id,
        payload=payment.invoice_payload,
        amount=payment.total_amount
    )

    exp_str = res["expires_at"].strftime("%d.%m.%Y") if res.get("expires_at") else "30 дней"

    await message.answer(
        f"🎉 <b>Оплата успешно получена!</b>\n\n"
        f"Подписка <b>{res['plan'].upper()}</b> активирована до <b>{exp_str}</b>.\n\n"

        f"Вам открыт полный доступ:\n"
        f"✅ Все 9 источников вакансий и заказов\n"
        f"✅ AI-генератор сопроводительных писем\n"
        f"✅ Персональный Gap-анализ резюме\n"
        f"✅ Канбан-трекер откликов (/tracker)\n\n"
        f"Удачного поиска и скорейшего оффера!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📊 Открыть трекер откликов", callback_data="open_tracker"),
            InlineKeyboardButton(text="🔍 Найти вакансии", callback_data="search_vacancies")
        ]])
    )
