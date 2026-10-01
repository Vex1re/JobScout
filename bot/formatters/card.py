import html
from typing import Dict, Any, List, Optional
from core.database.models import Vacancy, Resume, User


def format_salary(salary_min: Optional[int], salary_max: Optional[int], currency: str = "RUB") -> str:
    """Formats salary bounds into readable string."""
    curr_symbol = "₽" if currency in ["RUB", "RUR"] else currency
    if salary_min and salary_max:
        return f"{salary_min:,} — {salary_max:,} {curr_symbol}".replace(",", " ")
    elif salary_min:
        return f"от {salary_min:,} {curr_symbol}".replace(",", " ")
    elif salary_max:
        return f"до {salary_max:,} {curr_symbol}".replace(",", " ")
    return "Не указана (Договорная)"


def get_score_badge(score: int) -> str:
    if score >= 80:
        return f"🟢 <b>{score}% Совпадение</b> [Отличный матч]"
    elif score >= 60:
        return f"🟡 <b>{score}% Совпадение</b> [Хороший матч]"
    elif score >= 45:
        return f"🟠 <b>{score}% Совпадение</b> [Частичное]"
    else:
        return f"⚪ <b>{score}% Совпадение</b>"


def format_source_badge(source: str) -> str:
    badges = {
        "hh": "💼 HeadHunter",
        "habr": "🚀 Хабр Карьера",
        "kwork": "⚡ Kwork (Фриланс)",
        "rabota": "👔 Работа.ру"
    }
    return badges.get(source, source.capitalize())


def format_vacancy_card(vacancy: Vacancy, match_info: Dict[str, Any]) -> str:
    """
    Renders an aesthetically pleasing, informative Telegram HTML card for a vacancy.
    """
    score = match_info.get("score", 0)
    matched_skills = match_info.get("matched_skills", [])
    missing_skills = match_info.get("missing_skills", [])
    reason = match_info.get("reason", "")
    
    score_badge = get_score_badge(score)
    source_badge = format_source_badge(vacancy.source)
    salary_str = format_salary(vacancy.salary_min, vacancy.salary_max, vacancy.currency)
    
    if vacancy.is_freelance:
        format_str = "⚡ Фриланс проект"
    elif vacancy.is_remote:
        format_str = "🏠 Удаленка"
        if vacancy.city and vacancy.city != "Удаленно":
            format_str += f" (📍 {html.escape(vacancy.city)})"
    else:
        if vacancy.city:
            format_str = f"🏢 Офис (📍 {html.escape(vacancy.city)})"
        else:
            format_str = "🏢 Офис / Гибрид"

    # Red flag & safety check badge
    if vacancy.risk_level == "safe":
        safety_badge = "🛡️ <b>Безопасность:</b> ✅ Чистая вакансия (ред-флагов не найдено)"
    elif vacancy.risk_level == "warning":
        flags_text = "\n".join([f"  • {flag}" for flag in vacancy.red_flags])
        safety_badge = f"🛡️ <b>Безопасность:</b> ⚠️ <b>Обнаружены предупреждения:</b>\n{flags_text}"
    else:
        safety_badge = "🛡️ <b>Безопасность:</b> ⛔ Высокий риск мошенничества!"

    # Matched skills breakdown
    skills_text = ""
    if matched_skills:
        skills_text += f"\n✅ <b>Ваши навыки:</b> {', '.join(matched_skills[:8])}"
    if missing_skills:
        skills_text += f"\n⚡ <b>В вакансии требуется еще:</b> {', '.join(missing_skills[:5])}"

    # Short clean description
    clean_desc = vacancy.description.strip()
    if len(clean_desc) > 300:
        clean_desc = clean_desc[:297] + "..."
    clean_desc = html.escape(clean_desc)

    card = (
        f"🎯 {score_badge}\n\n"
        f"📌 <b>{html.escape(vacancy.title)}</b>\n"
        f"🏢 <b>Компания:</b> {html.escape(vacancy.company)}\n"
        f"🌐 <b>Источник:</b> {source_badge} | {format_str}\n"
        f"💰 <b>Зарплата / Бюджет:</b> <code>{salary_str}</code>\n"
        f"{skills_text}\n\n"
        f"{safety_badge}\n\n"
        f"📝 <b>Краткое описание:</b>\n<i>{clean_desc}</i>"
    )
    return card


def format_profile_view(user: User, resume: Optional[Resume]) -> str:
    """Renders profile and current active resume overview."""
    if not resume:
        return (
            "👤 <b>Ваш профиль в JobScout Bot</b>\n\n"
            "❌ <b>Резюме еще не загружено!</b>\n\n"
            "Чтобы бот находил для вас релевантные вакансии на HH, Хабр Карьере, "
            "Kwork и Работа.ру, отправьте ваше резюме файлом (PDF/DOCX) или текстом."
        )

    skills_formatted = ", ".join(resume.skills) if resume.skills else "Не определены"
    salary_exp = f"{resume.salary_expectation:,} ₽".replace(",", " ") if resume.salary_expectation else "Не указана"

    city_display = html.escape(user.city) if user.city else "Любой город"
    remote_status = "Да ✅" if user.remote_only else "Нет ❌ (Все форматы)"
    freelance_status = "Да ✅" if user.include_freelance else "Нет ❌"
    notify_status = "Включены 🔔" if user.auto_notify else "Отключены 🔕"

    return (
        f"👤 <b>Ваш профиль разработчика</b>\n\n"
        f"🎯 <b>Целевая позиция:</b> {html.escape(resume.title)}\n"
        f"💼 <b>Грейд:</b> {resume.grade} (~{resume.years_of_experience} г. опыта)\n"
        f"💰 <b>Желаемая ЗП:</b> {salary_exp}\n\n"
        f"🛠️ <b>Распознанный стек ({len(resume.skills)}):</b>\n"
        f"<code>{html.escape(skills_formatted)}</code>\n\n"
        f"⚙️ <b>Настройки поиска:</b>\n"
        f"• 📍 Город поиска: {city_display}\n"
        f"• Только удаленка: {remote_status}\n"
        f"• Включать фриланс заказы: {freelance_status}\n"
        f"• Автопоиск в фоне: {notify_status}\n\n"
        f"<i>Вы можете в любой момент обновить резюме или стек по кнопкам ниже.</i>"
    )
