import datetime
from typing import List, Optional
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    UniqueConstraint,
    Index,
    func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Preferences & filters
    auto_notify: Mapped[bool] = mapped_column(Boolean, default=True)
    min_salary: Mapped[int] = mapped_column(Integer, default=0)
    remote_only: Mapped[bool] = mapped_column(Boolean, default=False)
    include_freelance: Mapped[bool] = mapped_column(Boolean, default=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default=None)
    search_page_offset: Mapped[int] = mapped_column(Integer, default=0)
    last_query_index: Mapped[int] = mapped_column(Integer, default=0)
    enabled_sources: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True, default=None)
    llm_consent: Mapped[bool] = mapped_column(Boolean, default=False)

    def get_effective_sources(self) -> List[str]:
        from services.parser.manager import ALL_SOURCES
        if self.enabled_sources is not None and len(self.enabled_sources) > 0:
            sources: List[str] = []
            for s in self.enabled_sources:
                if s == "habr_freelance":
                    s = "freelance_ru"
                if s in ALL_SOURCES and s not in sources:
                    sources.append(s)
            return sources
        return list(ALL_SOURCES)
    
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    # Relationships
    resume: Mapped[Optional["Resume"]] = relationship("Resume", back_populates="user", uselist=False, cascade="all, delete-orphan")
    favorites: Mapped[List["UserFavorite"]] = relationship("UserFavorite", back_populates="user", cascade="all, delete-orphan")
    hidden_vacancies: Mapped[List["UserHidden"]] = relationship("UserHidden", back_populates="user", cascade="all, delete-orphan")
    matches: Mapped[List["UserMatch"]] = relationship("UserMatch", back_populates="user", cascade="all, delete-orphan")
    viewed_vacancies: Mapped[List["UserViewed"]] = relationship("UserViewed", back_populates="user", cascade="all, delete-orphan")
    interactions: Mapped[List["UserInteraction"]] = relationship("UserInteraction", back_populates="user", cascade="all, delete-orphan")


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), unique=True)
    
    # Analyzed resume fields
    title: Mapped[str] = mapped_column(String(255), default="Специалист")
    grade: Mapped[str] = mapped_column(String(50), default="Middle") # Junior, Middle, Senior, Lead
    years_of_experience: Mapped[float] = mapped_column(Float, default=1.0)
    salary_expectation: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Skills stored as JSON list: ["python", "docker", "fastapi", ...]
    skills: Mapped[List[str]] = mapped_column(JSON, default=list)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    user: Mapped["User"] = relationship("User", back_populates="resume")


class Vacancy(Base):
    __tablename__ = "vacancies"
    __table_args__ = (
        Index("ix_vacancies_city_remote", "city", "is_remote"),
        Index("ix_vacancies_canonical_id", "canonical_id"),
        UniqueConstraint("source", "external_id", name="uq_source_external_id"),
    )

    id: Mapped[str] = mapped_column(String(255), primary_key=True) # e.g. "hh_12345", "kwork_987"
    source: Mapped[str] = mapped_column(String(50), index=True) # hh, habr, kwork, rabota
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    canonical_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    company: Mapped[str] = mapped_column(String(255), default="Не указана")
    url: Mapped[str] = mapped_column(Text)
    
    # Salary
    salary_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    salary_from: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    salary_to: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(20), default="RUB")
    salary_gross_net: Mapped[str] = mapped_column(String(20), default="unknown")
    salary_rub_normalized: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Description & Content
    description: Mapped[str] = mapped_column(Text, default="")
    snippet: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    requirements: Mapped[List[str]] = mapped_column(JSON, default=list) # Extracted skills required
    skills: Mapped[List[str]] = mapped_column(JSON, default=list)
    
    # Location & format
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False)
    remote_scope: Mapped[str] = mapped_column(String(50), default="unknown") # worldwide, RU, US-only, unknown
    is_freelance: Mapped[bool] = mapped_column(Boolean, default=False)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default=None)
    city_norm: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default=None)
    
    # Experience & Grade
    min_experience: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    max_experience: Mapped[Optional[float]] = mapped_column(Float, nullable=True, default=None)
    required_experience: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default=None)
    target_grade: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default=None)
    grade: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default=None)
    grade_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    
    # Scam & Red flag analysis
    risk_level: Mapped[str] = mapped_column(String(50), default="safe") # safe, warning, blocked
    red_flag_level: Mapped[str] = mapped_column(String(50), default="safe")
    red_flags: Mapped[List[str]] = mapped_column(JSON, default=list)
    
    # Timestamps & status
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    first_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    favorites: Mapped[List["UserFavorite"]] = relationship("UserFavorite", back_populates="vacancy", cascade="all, delete-orphan")
    matches: Mapped[List["UserMatch"]] = relationship("UserMatch", back_populates="vacancy", cascade="all, delete-orphan")
    views: Mapped[List["UserViewed"]] = relationship("UserViewed", back_populates="vacancy", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        # Sync synonyms if not explicitly provided
        if "salary_from" not in kwargs and "salary_min" in kwargs:
            kwargs["salary_from"] = kwargs["salary_min"]
        elif "salary_min" not in kwargs and "salary_from" in kwargs:
            kwargs["salary_min"] = kwargs["salary_from"]

        if "salary_to" not in kwargs and "salary_max" in kwargs:
            kwargs["salary_to"] = kwargs["salary_max"]
        elif "salary_max" not in kwargs and "salary_to" in kwargs:
            kwargs["salary_max"] = kwargs["salary_to"]

        if "skills" not in kwargs and "requirements" in kwargs:
            kwargs["skills"] = kwargs["requirements"]
        elif "requirements" not in kwargs and "skills" in kwargs:
            kwargs["requirements"] = kwargs["skills"]

        if "city_norm" not in kwargs and "city" in kwargs:
            kwargs["city_norm"] = kwargs["city"]
        elif "city" not in kwargs and "city_norm" in kwargs:
            kwargs["city"] = kwargs["city_norm"]

        if "grade" not in kwargs and "target_grade" in kwargs:
            kwargs["grade"] = kwargs["target_grade"]
        elif "target_grade" not in kwargs and "grade" in kwargs:
            kwargs["target_grade"] = kwargs["grade"]

        if "red_flag_level" not in kwargs and "risk_level" in kwargs:
            kwargs["red_flag_level"] = kwargs["risk_level"]
        elif "risk_level" not in kwargs and "red_flag_level" in kwargs:
            kwargs["risk_level"] = kwargs["red_flag_level"]

        if "external_id" not in kwargs and "id" in kwargs:
            vid = str(kwargs["id"])
            kwargs["external_id"] = vid.split("_", 1)[-1] if "_" in vid else vid

        super().__init__(**kwargs)


class UserViewed(Base):
    __tablename__ = "user_viewed"
    __table_args__ = (
        UniqueConstraint("user_id", "vacancy_id", name="uq_user_vacancy_viewed"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), index=True)
    vacancy_id: Mapped[str] = mapped_column(String(255), ForeignKey("vacancies.id", ondelete="CASCADE"), index=True)
    view_count: Mapped[int] = mapped_column(Integer, default=1)
    first_viewed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_viewed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    user: Mapped["User"] = relationship("User", back_populates="viewed_vacancies")
    vacancy: Mapped["Vacancy"] = relationship("Vacancy", back_populates="views")


class UserFavorite(Base):
    __tablename__ = "user_favorites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), index=True)
    vacancy_id: Mapped[str] = mapped_column(String(255), ForeignKey("vacancies.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped["User"] = relationship("User", back_populates="favorites")
    vacancy: Mapped["Vacancy"] = relationship("Vacancy", back_populates="favorites")


class UserHidden(Base):
    __tablename__ = "user_hidden"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), index=True)
    vacancy_id: Mapped[str] = mapped_column(String(255), ForeignKey("vacancies.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped["User"] = relationship("User", back_populates="hidden_vacancies")


class UserMatch(Base):
    __tablename__ = "user_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), index=True)
    vacancy_id: Mapped[str] = mapped_column(String(255), ForeignKey("vacancies.id", ondelete="CASCADE"), index=True)
    score: Mapped[int] = mapped_column(Integer) # 0 to 100
    matched_skills: Mapped[List[str]] = mapped_column(JSON, default=list)
    missing_skills: Mapped[List[str]] = mapped_column(JSON, default=list)
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped["User"] = relationship("User", back_populates="matches")
    vacancy: Mapped["Vacancy"] = relationship("Vacancy", back_populates="matches")


class UserInteraction(Base):
    __tablename__ = "user_interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), index=True)
    vacancy_canonical_id: Mapped[str] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(50))  # favorite, hide, apply_click
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped["User"] = relationship("User", back_populates="interactions")
