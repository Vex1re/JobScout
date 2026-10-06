from typing import List, Optional, Tuple
from sqlalchemy import select, delete, desc, and_, not_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from core.database.models import (
    User,
    Resume,
    Vacancy,
    UserFavorite,
    UserHidden,
    UserMatch,
    UserViewed,
    utc_now
)


class UserRepository:
    @staticmethod
    async def get_or_create_user(
        session: AsyncSession,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None
    ) -> User:
        stmt = (
            select(User)
            .options(selectinload(User.resume))
            .where(User.telegram_id == telegram_id)
        )
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        
        if not user:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                is_active=True
            )
            session.add(user)
            await session.commit()
            # Reload with relationships
            res = await session.execute(stmt)
            user = res.scalar_one()
        else:
            # Update username/first_name if changed
            if username and user.username != username:
                user.username = username
            if first_name and user.first_name != first_name:
                user.first_name = first_name
            await session.commit()
            
        return user

    @staticmethod
    async def update_preferences(
        session: AsyncSession,
        telegram_id: int,
        auto_notify: Optional[bool] = None,
        min_salary: Optional[int] = None,
        remote_only: Optional[bool] = None,
        include_freelance: Optional[bool] = None,
        city: Optional[str] = None,
        search_page_offset: Optional[int] = None,
        last_query_index: Optional[int] = None,
        enabled_sources: Optional[List[str]] = None
    ) -> Optional[User]:
        stmt = select(User).where(User.telegram_id == telegram_id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            return None
            
        if auto_notify is not None:
            user.auto_notify = auto_notify
        if min_salary is not None:
            user.min_salary = min_salary
        if remote_only is not None:
            user.remote_only = remote_only
        if include_freelance is not None:
            user.include_freelance = include_freelance
        if city is not None:
            user.city = None if city.strip().lower() in ["", "любой", "все", "любой город", "none", "null"] else city.strip()
        if search_page_offset is not None:
            user.search_page_offset = search_page_offset
        if last_query_index is not None:
            user.last_query_index = last_query_index
        if enabled_sources is not None:
            user.enabled_sources = enabled_sources
            
        await session.commit()
        await session.refresh(user)
        return user

    @staticmethod
    async def toggle_source(
        session: AsyncSession,
        telegram_id: int,
        source_name: str
    ) -> Tuple[bool, List[str]]:
        from services.parser.manager import ALL_SOURCES
        stmt = select(User).where(User.telegram_id == telegram_id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            return False, list(ALL_SOURCES)

        current = list(user.get_effective_sources())
        if source_name in current:
            # Cannot disable if it's the only one left
            if len(current) <= 1:
                return False, current
            current.remove(source_name)
        else:
            if source_name in ALL_SOURCES:
                current.append(source_name)

        user.enabled_sources = current
        await session.commit()
        await session.refresh(user)
        return True, user.get_effective_sources()

    @staticmethod
    async def set_sources(
        session: AsyncSession,
        telegram_id: int,
        sources: List[str]
    ) -> Optional[User]:
        from services.parser.manager import ALL_SOURCES
        stmt = select(User).where(User.telegram_id == telegram_id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if not user:
            return None
        valid_sources = [s for s in sources if s in ALL_SOURCES]
        user.enabled_sources = valid_sources if valid_sources else list(ALL_SOURCES)
        await session.commit()
        await session.refresh(user)
        return user

    @staticmethod
    async def increment_search_offsets(
        session: AsyncSession,
        telegram_id: int,
        offset_inc: int = 1,
        query_index_inc: int = 1
    ) -> None:
        stmt = select(User).where(User.telegram_id == telegram_id)
        res = await session.execute(stmt)
        user = res.scalar_one_or_none()
        if user:
            user.search_page_offset = (user.search_page_offset or 0) + offset_inc
            user.last_query_index = (user.last_query_index or 0) + query_index_inc
            await session.commit()

    @staticmethod
    async def get_active_users_with_resumes(session: AsyncSession) -> List[User]:
        stmt = (
            select(User)
            .options(selectinload(User.resume))
            .where(User.is_active == True, User.auto_notify == True)
        )
        res = await session.execute(stmt)
        users = res.scalars().all()
        return [u for u in users if u.resume is not None and (len(u.resume.skills) > 0 or bool(u.resume.title))]

    @staticmethod
    async def delete_user_all_data(session: AsyncSession, telegram_id: int) -> bool:
        """Deletes all user personal data, resume, history, and matches (GDPR / 152-ФЗ compliance)."""
        await session.execute(delete(Resume).where(Resume.user_id == telegram_id))
        await session.execute(delete(UserFavorite).where(UserFavorite.user_id == telegram_id))
        await session.execute(delete(UserHidden).where(UserHidden.user_id == telegram_id))
        await session.execute(delete(UserMatch).where(UserMatch.user_id == telegram_id))
        await session.execute(delete(UserViewed).where(UserViewed.user_id == telegram_id))
        stmt = delete(User).where(User.telegram_id == telegram_id)
        res = await session.execute(stmt)
        await session.commit()
        return res.rowcount > 0


class ResumeRepository:
    @staticmethod
    async def save_or_update_resume(
        session: AsyncSession,
        user_id: int,
        title: str,
        grade: str,
        years_of_experience: float,
        skills: List[str],
        raw_text: str,
        salary_expectation: Optional[int] = None
    ) -> Resume:
        stmt = select(Resume).where(Resume.user_id == user_id)
        res = await session.execute(stmt)
        resume = res.scalar_one_or_none()
        
        if resume:
            resume.title = title
            resume.grade = grade
            resume.years_of_experience = years_of_experience
            resume.skills = skills
            resume.raw_text = raw_text
            resume.salary_expectation = salary_expectation
        else:
            resume = Resume(
                user_id=user_id,
                title=title,
                grade=grade,
                years_of_experience=years_of_experience,
                skills=skills,
                raw_text=raw_text,
                salary_expectation=salary_expectation
            )
            session.add(resume)
            
        await session.commit()
        await session.refresh(resume)
        return resume

    @staticmethod
    async def get_resume(session: AsyncSession, user_id: int) -> Optional[Resume]:
        stmt = select(Resume).where(Resume.user_id == user_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()


class VacancyRepository:
    @staticmethod
    async def upsert_vacancies(session: AsyncSession, vacancies_data: List[dict]) -> int:
        """Upsert vacancies from aggregators. Returns count of newly added vacancies."""
        added_count = 0
        for data in vacancies_data:
            vac_id = data.get("id")
            if not vac_id:
                continue
            stmt = select(Vacancy).where(Vacancy.id == vac_id)
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()
            
            if not existing:
                vac = Vacancy(
                    id=vac_id,
                    source=data.get("source", "unknown"),
                    title=data.get("title", ""),
                    company=data.get("company", "Не указана"),
                    url=data.get("url", ""),
                    salary_min=data.get("salary_min"),
                    salary_max=data.get("salary_max"),
                    currency=data.get("currency", "RUB"),
                    description=data.get("description", ""),
                    requirements=data.get("requirements", []),
                    is_remote=data.get("is_remote", False),
                    is_freelance=data.get("is_freelance", False),
                    city=data.get("city"),
                    min_experience=data.get("min_experience"),
                    max_experience=data.get("max_experience"),
                    target_grade=data.get("target_grade"),
                    risk_level=data.get("risk_level", "safe"),
                    red_flags=data.get("red_flags", []),
                    published_at=data.get("published_at")
                )
                session.add(vac)
                added_count += 1
            else:
                # Update status or details if needed
                existing.risk_level = data.get("risk_level", existing.risk_level)
                existing.red_flags = data.get("red_flags", existing.red_flags)
                if data.get("city"):
                    existing.city = data.get("city")
                if data.get("min_experience") is not None:
                    existing.min_experience = data.get("min_experience")
                if data.get("max_experience") is not None:
                    existing.max_experience = data.get("max_experience")
                if data.get("target_grade"):
                    existing.target_grade = data.get("target_grade")
                
        await session.commit()
        return added_count

    @staticmethod
    async def get_vacancy(session: AsyncSession, vacancy_id: str) -> Optional[Vacancy]:
        stmt = select(Vacancy).where(Vacancy.id == vacancy_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_unhidden_vacancies(
        session: AsyncSession,
        user_id: int,
        exclude_blocked: bool = True,
        remote_only: bool = False,
        include_freelance: bool = True,
        min_salary: int = 0,
        exclude_viewed: bool = True,
        user_city: Optional[str] = None,
        allowed_sources: Optional[List[str]] = None,
        limit: int = 500
    ) -> List[Vacancy]:
        hidden_stmt = select(UserHidden.vacancy_id).where(UserHidden.user_id == user_id)
        conditions = [not_(Vacancy.id.in_(hidden_stmt))]

        if exclude_viewed:
            viewed_stmt = select(UserViewed.vacancy_id).where(UserViewed.user_id == user_id)
            conditions.append(not_(Vacancy.id.in_(viewed_stmt)))
        
        if exclude_blocked:
            conditions.append(Vacancy.risk_level != "blocked")
            
        if remote_only:
            conditions.append(Vacancy.is_remote == True)
            
        if not include_freelance:
            conditions.append(Vacancy.is_freelance == False)

        if allowed_sources:
            conditions.append(Vacancy.source.in_(allowed_sources))
            
        if min_salary > 0:
            # Vacancy matches if salary_max >= min_salary or salary_min >= min_salary or salary not specified
            conditions.append(
                (Vacancy.salary_max >= min_salary) | 
                (Vacancy.salary_min >= min_salary) | 
                (Vacancy.salary_min.is_(None) & Vacancy.salary_max.is_(None))
            )

        if user_city and not remote_only:
            from services.parser.normalizer import CityNormalizer
            if user_city.strip().lower() not in ["", "любой", "все", "любой город", "none", "null", "all", "any"]:
                norm_user_city = CityNormalizer.normalize(user_city)
                if norm_user_city and norm_user_city != "Удаленно":
                    conditions.append(
                        (Vacancy.is_remote == True) | 
                        (Vacancy.city == norm_user_city) | 
                        (Vacancy.city == "Удаленно") | 
                        (Vacancy.city.is_(None))
                    )
            
        stmt = select(Vacancy).where(and_(*conditions)).order_by(desc(Vacancy.published_at)).limit(limit)
        res = await session.execute(stmt)
        vacancies = list(res.scalars().all())

        if user_city and not remote_only:
            from services.parser.normalizer import CityNormalizer
            vacancies = [
                v for v in vacancies
                if CityNormalizer.is_match(user_city=user_city, vacancy_city=v.city, is_remote=v.is_remote)
            ]

        return vacancies


class InteractionRepository:
    @staticmethod
    async def toggle_favorite(session: AsyncSession, user_id: int, vacancy_id: str) -> bool:
        stmt = select(UserFavorite).where(
            UserFavorite.user_id == user_id,
            UserFavorite.vacancy_id == vacancy_id
        )
        res = await session.execute(stmt)
        fav = res.scalar_one_or_none()
        
        if fav:
            await session.delete(fav)
            await session.commit()
            return False # removed
        else:
            new_fav = UserFavorite(user_id=user_id, vacancy_id=vacancy_id)
            session.add(new_fav)
            await session.commit()
            return True # added

    @staticmethod
    async def is_favorite(session: AsyncSession, user_id: int, vacancy_id: str) -> bool:
        stmt = select(UserFavorite).where(
            UserFavorite.user_id == user_id,
            UserFavorite.vacancy_id == vacancy_id
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none() is not None

    @staticmethod
    async def get_favorites(session: AsyncSession, user_id: int) -> List[Vacancy]:
        stmt = (
            select(Vacancy)
            .join(UserFavorite, UserFavorite.vacancy_id == Vacancy.id)
            .where(UserFavorite.user_id == user_id)
            .order_by(desc(UserFavorite.created_at))
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def hide_vacancy(session: AsyncSession, user_id: int, vacancy_id: str) -> None:
        stmt = select(UserHidden).where(
            UserHidden.user_id == user_id,
            UserHidden.vacancy_id == vacancy_id
        )
        res = await session.execute(stmt)
        if not res.scalar_one_or_none():
            hidden = UserHidden(user_id=user_id, vacancy_id=vacancy_id)
            session.add(hidden)
            await session.commit()

    @staticmethod
    async def mark_as_viewed(session: AsyncSession, user_id: int, vacancy_id: str) -> None:
        stmt = select(UserViewed).where(
            UserViewed.user_id == user_id,
            UserViewed.vacancy_id == vacancy_id
        )
        res = await session.execute(stmt)
        viewed = res.scalar_one_or_none()
        now = utc_now()
        if viewed:
            viewed.view_count += 1
            viewed.last_viewed_at = now
        else:
            viewed = UserViewed(
                user_id=user_id,
                vacancy_id=vacancy_id,
                view_count=1,
                first_viewed_at=now,
                last_viewed_at=now
            )
            session.add(viewed)
        await session.commit()

    @staticmethod
    async def reset_viewed_history(session: AsyncSession, user_id: int) -> int:
        stmt = delete(UserViewed).where(UserViewed.user_id == user_id)
        res = await session.execute(stmt)
        await session.commit()
        return res.rowcount

    @staticmethod
    async def save_or_update_match(
        session: AsyncSession,
        user_id: int,
        vacancy_id: str,
        score: int,
        matched_skills: List[str],
        missing_skills: List[str],
        is_sent: bool = False
    ) -> UserMatch:
        stmt = select(UserMatch).where(
            UserMatch.user_id == user_id,
            UserMatch.vacancy_id == vacancy_id
        )
        res = await session.execute(stmt)
        match = res.scalar_one_or_none()
        if match:
            match.score = score
            match.matched_skills = matched_skills
            match.missing_skills = missing_skills
            if is_sent:
                match.is_sent = True
        else:
            match = UserMatch(
                user_id=user_id,
                vacancy_id=vacancy_id,
                score=score,
                matched_skills=matched_skills,
                missing_skills=missing_skills,
                is_sent=is_sent
            )
            session.add(match)
        await session.commit()
        return match
