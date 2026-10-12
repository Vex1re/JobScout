from typing import List, Optional, Tuple, Set
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
    UserInteraction,
    Subscription,
    Entitlement,
    JobApplicationTracker,
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
        """Deletes all user personal data, resume, history, and matches."""
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
                    external_id=data.get("external_id") or (vac_id.split("_", 1)[-1] if "_" in vac_id else vac_id),
                    canonical_id=data.get("canonical_id"),
                    source=data.get("source", "unknown"),
                    title=data.get("title", ""),
                    company=data.get("company", "Не указана"),
                    url=data.get("url", ""),
                    salary_min=data.get("salary_min"),
                    salary_max=data.get("salary_max"),
                    salary_from=data.get("salary_from") or data.get("salary_min"),
                    salary_to=data.get("salary_to") or data.get("salary_max"),
                    currency=data.get("currency", "RUB"),
                    salary_gross_net=data.get("salary_gross_net", "unknown"),
                    salary_rub_normalized=data.get("salary_rub_normalized"),
                    description=data.get("description", ""),
                    snippet=data.get("snippet"),
                    requirements=data.get("requirements", []),
                    skills=data.get("skills") or data.get("requirements", []),
                    is_remote=data.get("is_remote", False),
                    remote_scope=data.get("remote_scope", "unknown"),
                    is_freelance=data.get("is_freelance", False),
                    city=data.get("city"),
                    city_norm=data.get("city_norm") or data.get("city"),
                    min_experience=data.get("min_experience"),
                    max_experience=data.get("max_experience"),
                    required_experience=data.get("required_experience"),
                    target_grade=data.get("target_grade"),
                    grade=data.get("grade") or data.get("target_grade"),
                    grade_confidence=data.get("grade_confidence", 1.0),
                    risk_level=data.get("risk_level", "safe"),
                    red_flag_level=data.get("red_flag_level") or data.get("risk_level", "safe"),
                    red_flags=data.get("red_flags", []),
                    published_at=data.get("published_at"),
                    first_seen_at=utc_now(),
                    last_seen_at=utc_now(),
                    is_active=True
                )
                session.add(vac)
                added_count += 1
            else:
                existing.last_seen_at = utc_now()
                existing.is_active = True
                if data.get("canonical_id"):
                    existing.canonical_id = data.get("canonical_id")
                if data.get("salary_rub_normalized") is not None:
                    existing.salary_rub_normalized = data.get("salary_rub_normalized")
                if data.get("snippet"):
                    existing.snippet = data.get("snippet")
                if data.get("remote_scope") and existing.remote_scope == "unknown":
                    existing.remote_scope = data.get("remote_scope")
                existing.risk_level = data.get("risk_level", existing.risk_level)
                existing.red_flags = data.get("red_flags", existing.red_flags)
                if data.get("city"):
                    existing.city = data.get("city")
                    existing.city_norm = data.get("city")
                if data.get("min_experience") is not None:
                    existing.min_experience = data.get("min_experience")
                if data.get("max_experience") is not None:
                    existing.max_experience = data.get("max_experience")
                if data.get("target_grade"):
                    existing.target_grade = data.get("target_grade")
                    existing.grade = data.get("target_grade")
                
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

    @staticmethod
    async def log_interaction(
        session: AsyncSession,
        user_id: int,
        vacancy_canonical_id: str,
        action: str
    ) -> UserInteraction:
        """Logs user interaction (favorite, hide, apply_click) for recommendation relevance."""
        interaction = UserInteraction(
            user_id=user_id,
            vacancy_canonical_id=vacancy_canonical_id,
            action=action,
            created_at=utc_now()
        )
        session.add(interaction)
        await session.commit()
        return interaction

    @staticmethod
    async def get_hidden_canonical_ids(session: AsyncSession, user_id: int) -> Set[str]:
        """Returns set of vacancy_canonical_ids hidden by user."""
        stmt = select(UserInteraction.vacancy_canonical_id).where(
            UserInteraction.user_id == user_id,
            UserInteraction.action == "hide"
        )
        res = await session.execute(stmt)
        return set(res.scalars().all())

    @staticmethod
    async def get_positive_interactions(
        session: AsyncSession,
        user_id: int,
        action: Optional[str] = None
    ) -> List[UserInteraction]:
        """Returns recent positive interactions (favorite, apply_click) to boost similar items."""
        actions = [action] if action else ["favorite", "apply_click"]
        stmt = (
            select(UserInteraction)
            .where(
                UserInteraction.user_id == user_id,
                UserInteraction.action.in_(actions)
            )
            .order_by(desc(UserInteraction.created_at))
            .limit(100)
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())


class SubscriptionRepository:
    PLAN_ENTITLEMENTS = {
        "free": set(),
        "pro": {
            "unlimited_sources",
            "instant_notifications",
            "ai_cover_letter",
            "ai_gap_analysis",
            "kanban_tracker",
        },
        "team": {
            "unlimited_sources",
            "instant_notifications",
            "ai_cover_letter",
            "ai_gap_analysis",
            "kanban_tracker",
            "team_analytics",
        }
    }

    @staticmethod
    async def get_subscription(session: AsyncSession, user_id: int) -> Optional[Subscription]:
        stmt = select(Subscription).where(Subscription.user_id == user_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def has_active_subscription(session: AsyncSession, user_id: int) -> bool:
        import datetime
        sub = await SubscriptionRepository.get_subscription(session, user_id)
        if not sub or not sub.is_active or sub.plan == "free":
            return False
        if sub.expires_at:
            exp_tz = sub.expires_at.replace(tzinfo=datetime.timezone.utc) if sub.expires_at.tzinfo is None else sub.expires_at
            if exp_tz < utc_now():
                return False
        return True

    @staticmethod
    async def create_or_update_subscription(
        session: AsyncSession,
        user_id: int,
        plan: str,
        duration_days: int = 30
    ) -> Subscription:
        import datetime
        sub = await SubscriptionRepository.get_subscription(session, user_id)
        now = utc_now()
        new_expires = now + datetime.timedelta(days=duration_days)

        if sub:
            if sub.expires_at:
                exp_tz = sub.expires_at.replace(tzinfo=datetime.timezone.utc) if sub.expires_at.tzinfo is None else sub.expires_at
                if exp_tz > now:
                    new_expires = exp_tz + datetime.timedelta(days=duration_days)
            sub.plan = plan
            sub.expires_at = new_expires
            sub.is_active = True
            sub.updated_at = now
        else:
            sub = Subscription(
                user_id=user_id,
                plan=plan,
                expires_at=new_expires,
                is_active=True,
                created_at=now,
                updated_at=now
            )
            session.add(sub)

        await session.commit()
        await session.refresh(sub)
        return sub

    @staticmethod
    async def grant_entitlement(
        session: AsyncSession,
        user_id: int,
        feature: str,
        duration_days: Optional[int] = 30
    ) -> Entitlement:
        import datetime
        now = utc_now()
        expires_at = now + datetime.timedelta(days=duration_days) if duration_days else None

        stmt = select(Entitlement).where(
            Entitlement.user_id == user_id,
            Entitlement.feature == feature
        )
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            existing.expires_at = expires_at
            ent = existing
        else:
            ent = Entitlement(
                user_id=user_id,
                feature=feature,
                expires_at=expires_at,
                created_at=now
            )
            session.add(ent)

        await session.commit()
        return ent

    @staticmethod
    async def get_user_entitlements(session: AsyncSession, user_id: int) -> Set[str]:
        import datetime
        active_features = set()

        # If user has active subscription, add plan entitlements
        sub = await SubscriptionRepository.get_subscription(session, user_id)
        if sub and sub.is_active and sub.plan in SubscriptionRepository.PLAN_ENTITLEMENTS:
            is_valid = True
            if sub.expires_at:
                exp_tz = sub.expires_at.replace(tzinfo=datetime.timezone.utc) if sub.expires_at.tzinfo is None else sub.expires_at
                if exp_tz <= utc_now():
                    is_valid = False
            if is_valid:
                active_features.update(SubscriptionRepository.PLAN_ENTITLEMENTS[sub.plan])

        # Query explicit standalone entitlements
        stmt = select(Entitlement).where(Entitlement.user_id == user_id)
        res = await session.execute(stmt)
        now = utc_now()
        for ent in res.scalars().all():
            if ent.expires_at is None:
                active_features.add(ent.feature)
            else:
                exp_tz = ent.expires_at.replace(tzinfo=datetime.timezone.utc) if ent.expires_at.tzinfo is None else ent.expires_at
                if exp_tz > now:
                    active_features.add(ent.feature)

        return active_features

    @staticmethod
    async def has_entitlement(session: AsyncSession, user_id: int, feature: str) -> bool:
        ents = await SubscriptionRepository.get_user_entitlements(session, user_id)
        return feature in ents


class TrackerRepository:
    @staticmethod
    async def create_or_update_application(
        session: AsyncSession,
        user_id: int,
        title: str,
        company: str,
        url: Optional[str] = None,
        vacancy_id: Optional[str] = None,
        vacancy_canonical_id: Optional[str] = None,
        status: str = "applied",
        notes: Optional[str] = None,
        salary_offered: Optional[int] = None
    ) -> JobApplicationTracker:
        stmt = select(JobApplicationTracker).where(
            JobApplicationTracker.user_id == user_id
        )
        if vacancy_canonical_id:
            stmt = stmt.where(JobApplicationTracker.vacancy_canonical_id == vacancy_canonical_id)
        elif vacancy_id:
            stmt = stmt.where(JobApplicationTracker.vacancy_id == vacancy_id)
        else:
            stmt = stmt.where(
                JobApplicationTracker.title == title,
                JobApplicationTracker.company == company
            )

        res = await session.execute(stmt)
        app = res.scalar_one_or_none()
        now = utc_now()

        if app:
            app.status = status
            if notes is not None:
                app.notes = notes
            if salary_offered is not None:
                app.salary_offered = salary_offered
            app.updated_at = now
        else:
            app = JobApplicationTracker(
                user_id=user_id,
                vacancy_id=vacancy_id,
                vacancy_canonical_id=vacancy_canonical_id,
                title=title,
                company=company,
                url=url,
                status=status,
                notes=notes,
                salary_offered=salary_offered,
                created_at=now,
                updated_at=now
            )
            session.add(app)

        await session.commit()
        await session.refresh(app)
        return app

    @staticmethod
    async def get_user_applications(
        session: AsyncSession,
        user_id: int,
        status: Optional[str] = None
    ) -> List[JobApplicationTracker]:
        stmt = select(JobApplicationTracker).where(JobApplicationTracker.user_id == user_id)
        if status:
            stmt = stmt.where(JobApplicationTracker.status == status)
        stmt = stmt.order_by(desc(JobApplicationTracker.updated_at))
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def update_status(
        session: AsyncSession,
        application_id: int,
        user_id: int,
        new_status: str
    ) -> Optional[JobApplicationTracker]:
        stmt = select(JobApplicationTracker).where(
            JobApplicationTracker.id == application_id,
            JobApplicationTracker.user_id == user_id
        )
        res = await session.execute(stmt)
        app = res.scalar_one_or_none()
        if not app:
            return None
        app.status = new_status
        app.updated_at = utc_now()
        await session.commit()
        await session.refresh(app)
        return app

    @staticmethod
    async def delete_application(
        session: AsyncSession,
        application_id: int,
        user_id: int
    ) -> bool:
        stmt = delete(JobApplicationTracker).where(
            JobApplicationTracker.id == application_id,
            JobApplicationTracker.user_id == user_id
        )
        res = await session.execute(stmt)
        await session.commit()
        return res.rowcount > 0
