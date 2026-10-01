import html
import io
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.repository import UserRepository, ResumeRepository
from services.resume_analyzer.extractor import ResumeExtractor
from services.ai.llm_helper import llm_helper
from bot.keyboards.reply import get_main_menu_keyboard, get_cancel_keyboard
from bot.keyboards.inline import (
    get_resume_confirm_keyboard,
    get_grade_selection_keyboard,
    get_profile_actions_keyboard
)
from bot.formatters.card import format_profile_view
from bot.states.profile import ProfileStates

router = Router(name="resume")


@router.message(Command("profile"))
@router.message(Command("resume"))
@router.message(F.text == "👤 Мой профиль и резюме")
async def show_profile(message: types.Message, session: AsyncSession):
    user = await UserRepository.get_or_create_user(
        session=session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )
    resume = await ResumeRepository.get_resume(session=session, user_id=user.telegram_id)
    text = format_profile_view(user, resume)
    await message.answer(text, reply_markup=get_profile_actions_keyboard())


@router.callback_query(F.data == "upload_resume_file")
@router.callback_query(F.data == "upload_resume_text")
async def prompt_resume_upload(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ProfileStates.waiting_for_resume)
    await callback.message.answer(
        "📄 <b>Отправьте ваше резюме:</b>\n\n"
        "• Прикрепите документ в формате <b>PDF</b> или <b>DOCX</b>\n"
        "• Либо просто скопируйте и пришлите текст резюме ответным сообщением.\n\n"
        "<i>Бот автоматически извлечет ваши технологии, грейд и опыт.</i>",
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()


@router.message(F.text == "❌ Отмена")
async def cancel_action(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=get_main_menu_keyboard())


@router.message(ProfileStates.waiting_for_resume, F.document)
async def process_resume_document(message: types.Message, state: FSMContext, bot: Bot):
    doc = message.document
    filename = (doc.file_name or "").lower()

    if not (filename.endswith(".pdf") or filename.endswith(".docx") or filename.endswith(".txt")):
        await message.answer("⚠️ Пожалуйста, отправьте файл в формате PDF, DOCX или TXT.")
        return

    status_msg = await message.answer("⏳ Анализирую файл резюме, пожалуйста, подождите...")

    # Download file in memory
    file_bytes_io = io.BytesIO()
    await bot.download(doc.file_id, destination=file_bytes_io)
    file_bytes = file_bytes_io.getvalue()

    extracted_text = ""
    if filename.endswith(".pdf"):
        extracted_text = ResumeExtractor.extract_text_from_pdf(file_bytes)
    elif filename.endswith(".docx"):
        extracted_text = ResumeExtractor.extract_text_from_docx(file_bytes)
    else:
        extracted_text = file_bytes.decode("utf-8", errors="ignore")

    if not extracted_text or len(extracted_text.strip()) < 30:
        await status_msg.edit_text(
            "⚠️ Не удалось прочитать текст из документа (возможно, это сканированное изображение). "
            "Пожалуйста, пришлите текст резюме обычным сообщением."
        )
        return

    await _process_parsed_text(status_msg, message.from_user.id, extracted_text, state)


@router.message(ProfileStates.waiting_for_resume, F.text)
async def process_resume_text(message: types.Message, state: FSMContext):
    if len(message.text.strip()) < 25:
        await message.answer("⚠️ Текст слишком короткий для резюме. Опишите ваши навыки и опыт подробнее.")
        return

    status_msg = await message.answer("⏳ Анализирую навыки и опыт...")
    await _process_parsed_text(status_msg, message.from_user.id, message.text, state)


async def _process_parsed_text(status_msg: types.Message, user_id: int, text: str, state: FSMContext):
    # Rule-based / deterministic extraction
    data = ResumeExtractor.parse_full_resume(text)

    # Optional AI deep enhancement if configured
    if llm_helper.is_available:
        ai_data = await llm_helper.analyze_resume_deep(text)
        if ai_data:
            if ai_data.get("title"):
                data["title"] = ai_data["title"]
            if ai_data.get("grade"):
                data["grade"] = ai_data["grade"]
            if ai_data.get("years_of_experience"):
                data["years_of_experience"] = float(ai_data["years_of_experience"])
            if ai_data.get("skills"):
                # Combine & deduplicate
                data["skills"] = sorted(list(set(data["skills"] + ai_data["skills"])))
            if ai_data.get("salary_expectation"):
                data["salary_expectation"] = int(ai_data["salary_expectation"])

    # If no skills detected, suggest default
    if not data["skills"]:
        data["skills"] = ["Python", "Git", "SQL"]

    # Save to state data
    await state.update_data(resume_data=data)
    await state.set_state(ProfileStates.confirm_skills)

    skills_str = ", ".join(data["skills"])
    salary_str = f"{data['salary_expectation']:,} ₽".replace(",", " ") if data.get("salary_expectation") else "Не указана"

    preview_text = (
        f"🎯 <b>Результат анализа вашего резюме:</b>\n\n"
        f"📌 <b>Позиция:</b> {html.escape(data['title'])}\n"
        f"💼 <b>Грейд:</b> {data['grade']} (~{data['years_of_experience']} г. опыта)\n"
        f"💰 <b>Желаемая ЗП:</b> {salary_str}\n\n"
        f"🛠️ <b>Распознанный стек ({len(data['skills'])}):</b>\n"
        f"<code>{html.escape(skills_str)}</code>\n\n"
        f"<i>Все верно или хотите скорректировать перед сохранением?</i>"
    )

    await status_msg.edit_text(preview_text, reply_markup=get_resume_confirm_keyboard())


@router.callback_query(F.data == "resume_confirm")
async def confirm_and_save_resume(callback: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    resume_data = data.get("resume_data")

    if not resume_data:
        await callback.answer("Данные устарели. Загрузите резюме заново.", show_alert=True)
        return

    # Ensure user exists
    await UserRepository.get_or_create_user(
        session=session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name
    )

    # Save to DB
    await ResumeRepository.save_or_update_resume(
        session=session,
        user_id=callback.from_user.id,
        title=resume_data.get("title", "Разработчик"),
        grade=resume_data.get("grade", "Middle"),
        years_of_experience=resume_data.get("years_of_experience", 1.0),
        skills=resume_data.get("skills", []),
        raw_text=resume_data.get("raw_text", ""),
        salary_expectation=resume_data.get("salary_expectation")
    )

    await state.clear()
    await callback.message.edit_text(
        "🎉 <b>Резюме успешно сохранено!</b>\n\n"
        "Теперь бот готов подбирать для вас самые подходящие и безопасные вакансии.\n"
        "Нажмите <b>«🔍 Найти вакансии»</b> в меню ниже!",
    )
    await callback.message.answer("Главное меню:", reply_markup=get_main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "resume_edit_skills")
async def prompt_edit_skills(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ProfileStates.editing_skills)
    await callback.message.answer(
        "✍️ <b>Введите список ваших навыков через запятую:</b>\n"
        "Например: <code>Python, FastAPI, Docker, PostgreSQL, Redis, Kafka</code>",
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()


@router.message(ProfileStates.editing_skills, F.text)
async def process_manual_skills(message: types.Message, state: FSMContext):
    raw_skills = [s.strip() for s in message.text.split(",") if s.strip()]
    if not raw_skills:
        await message.answer("⚠️ Введите хотя бы один навык.")
        return

    # Normalize skills
    normalized = []
    for s in raw_skills:
        found = ResumeExtractor.extract_skills(s)
        if found:
            normalized.extend(found)
        else:
            normalized.append(s.strip().capitalize())

    normalized = sorted(list(set(normalized)))

    data = await state.get_data()
    resume_data = data.get("resume_data") or {
        "title": "Software Developer",
        "grade": "Middle",
        "years_of_experience": 2.0,
        "raw_text": message.text
    }
    resume_data["skills"] = normalized
    await state.update_data(resume_data=resume_data)
    await state.set_state(ProfileStates.confirm_skills)

    skills_str = ", ".join(normalized)
    await message.answer(
        f"✅ <b>Стек обновлен!</b>\n\n"
        f"🛠️ <b>Текущие навыки ({len(normalized)}):</b>\n"
        f"<code>{html.escape(skills_str)}</code>",
        reply_markup=get_resume_confirm_keyboard()
    )


@router.callback_query(F.data == "resume_edit_grade")
async def prompt_edit_grade(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "💼 <b>Выберите ваш профессиональный грейд:</b>",
        reply_markup=get_grade_selection_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_grade_"))
async def process_grade_selection(callback: types.CallbackQuery, state: FSMContext):
    grade = callback.data.replace("set_grade_", "")
    data = await state.get_data()
    resume_data = data.get("resume_data") or {}
    resume_data["grade"] = grade
    await state.update_data(resume_data=resume_data)

    skills_str = ", ".join(resume_data.get("skills", []))
    await callback.message.edit_text(
        f"✅ <b>Грейд установлен: {grade}</b>\n\n"
        f"📌 <b>Позиция:</b> {html.escape(resume_data.get('title', 'Разработчик'))}\n"
        f"🛠️ <b>Стек:</b> <code>{html.escape(skills_str)}</code>",
        reply_markup=get_resume_confirm_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_resume_confirm")
async def back_to_resume_confirm(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    resume_data = data.get("resume_data") or {}
    skills_str = ", ".join(resume_data.get("skills", []))
    await callback.message.edit_text(
        f"🎯 <b>Ваше резюме:</b>\n\n"
        f"📌 <b>Позиция:</b> {html.escape(resume_data.get('title', 'Разработчик'))}\n"
        f"💼 <b>Грейд:</b> {resume_data.get('grade', 'Middle')}\n"
        f"🛠️ <b>Стек:</b> <code>{html.escape(skills_str)}</code>",
        reply_markup=get_resume_confirm_keyboard()
    )
    await callback.answer()
