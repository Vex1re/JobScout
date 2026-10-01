from aiogram.fsm.state import State, StatesGroup


class ProfileStates(StatesGroup):
    waiting_for_resume = State()
    confirm_skills = State()
    editing_skills = State()
    editing_grade = State()
    waiting_min_salary = State()
    waiting_custom_query = State()
