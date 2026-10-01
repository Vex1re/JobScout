import re
from typing import Optional, Dict


class CityNormalizer:
    """
    Normalizes city names, manages aliases/synonyms and performs city matching
    between candidate preferences and vacancies.
    """

    # Canonical mapping: lowercase alias -> Canonical City Name
    SYNONYMS: Dict[str, str] = {
        # Москва
        "москва": "Москва",
        "мск": "Москва",
        "moscow": "Москва",
        "moskva": "Москва",
        "город москва": "Москва",
        "г. москва": "Москва",
        "г.москва": "Москва",

        # Санкт-Петербург
        "санкт-петербург": "Санкт-Петербург",
        "санкт петербург": "Санкт-Петербург",
        "петербург": "Санкт-Петербург",
        "спб": "Санкт-Петербург",
        "питер": "Санкт-Петербург",
        "ленинград": "Санкт-Петербург",
        "saint petersburg": "Санкт-Петербург",
        "saint-petersburg": "Санкт-Петербург",
        "st petersburg": "Санкт-Петербург",
        "st. petersburg": "Санкт-Петербург",
        "г. санкт-петербург": "Санкт-Петербург",
        "г.спб": "Санкт-Петербург",

        # Казань
        "казань": "Казань",
        "kazan": "Казань",
        "г. казань": "Казань",

        # Екатеринбург
        "екатеринбург": "Екатеринбург",
        "екб": "Екатеринбург",
        "ekaterinburg": "Екатеринбург",
        "yekaterinburg": "Екатеринбург",
        "г. екатеринбург": "Екатеринбург",

        # Пермь
        "пермь": "Пермь",
        "perm": "Пермь",
        "г. пермь": "Пермь",

        # Новосибирск
        "новосибирск": "Новосибирск",
        "нск": "Новосибирск",
        "novosibirsk": "Новосибирск",
        "г. новосибирск": "Новосибирск",

        # Нижний Новгород
        "нижний новгород": "Нижний Новгород",
        "нн": "Нижний Новгород",
        "nizhny novgorod": "Нижний Новгород",
        "nizhniy novgorod": "Нижний Новгород",
        "г. нижний новгород": "Нижний Новгород",

        # Самара
        "самара": "Самара",
        "samara": "Самара",
        "г. самара": "Самара",

        # Ростов-на-Дону
        "ростов-на-дону": "Ростов-на-Дону",
        "ростов на дону": "Ростов-на-Дону",
        "ростов": "Ростов-на-Дону",
        "rostov-on-don": "Ростов-на-Дону",
        "г. ростов-на-дону": "Ростов-на-Дону",

        # Краснодар
        "краснодар": "Краснодар",
        "krasnodar": "Краснодар",
        "г. краснодар": "Краснодар",

        # Уфа
        "уфа": "Уфа",
        "ufa": "Уфа",
        "г. уфа": "Уфа",

        # Воронеж
        "воронеж": "Воронеж",
        "voronezh": "Воронеж",
        "г. воронеж": "Воронеж",

        # Челябинск
        "челябинск": "Челябинск",
        "chelyabinsk": "Челябинск",
        "г. челябинск": "Челябинск",

        # Красноярск
        "красноярск": "Красноярск",
        "krasnoyarsk": "Красноярск",
        "г. красноярск": "Красноярск",

        # Тюмень
        "тюмень": "Тюмень",
        "tyumen": "Тюмень",
        "г. тюмень": "Тюмень",

        # Омск
        "омск": "Омск",
        "omsk": "Омск",
        "г. омск": "Омск",

        # Томск
        "томск": "Томск",
        "tomsk": "Томск",
        "г. томск": "Томск",

        # Волгоград
        "волгоград": "Волгоград",
        "volgograd": "Волгоград",
        "г. волгоград": "Волгоград",

        # Саратов
        "саратов": "Саратов",
        "saratov": "Саратов",
        "г. саратов": "Саратов",

        # Минск
        "минск": "Минск",
        "minsk": "Минск",

        # Алматы
        "алматы": "Алматы",
        "алма-ата": "Алматы",
        "almaty": "Алматы",

        # Астана
        "астана": "Астана",
        "нур-султан": "Астана",
        "astana": "Астана",

        # Тбилиси
        "тбилиси": "Тбилиси",
        "tbilisi": "Тбилиси",

        # Ереван
        "ереван": "Ереван",
        "yerevan": "Ереван",

        # Белград
        "белград": "Белград",
        "belgrade": "Белград",

        # Удаленно
        "удаленно": "Удаленно",
        "удаленная работа": "Удаленно",
        "удаленка": "Удаленно",
        "remote": "Удаленно"
    }

    @classmethod
    def normalize(cls, city: Optional[str]) -> Optional[str]:
        """
        Normalizes a raw city name or text fragment into a canonical city name.
        """
        if not city:
            return None

        clean = city.strip()
        if not clean:
            return None

        lowered = clean.lower()

        # Remove common prefixes like 'г. ', 'город ', 'гор. '
        lowered_stripped = re.sub(r"^(г\.|город|гор\.)\s*", "", lowered).strip()

        # Wildcard city names mean no specific city
        if lowered in ["любой", "все", "любой город", "none", "null", "all", "any"] or \
           lowered_stripped in ["любой", "все", "любой город", "none", "null", "all", "any"]:
            return None

        # Direct dictionary match
        if lowered in cls.SYNONYMS:
            return cls.SYNONYMS[lowered]
        if lowered_stripped in cls.SYNONYMS:
            return cls.SYNONYMS[lowered_stripped]

        # Substring / pattern match for compound strings (e.g. "Москва, ЦАО", "г. Санкт-Петербург, м. Сенная")
        for alias, canonical in cls.SYNONYMS.items():
            if len(alias) >= 3:
                pattern = r"(?<![a-zA-Zа-яА-Я0-9_-])" + re.escape(alias) + r"(?![a-zA-Zа-яА-Я0-9_-])"
                if re.search(pattern, lowered):
                    return canonical

        # Generic title case cleanup
        words = [w.capitalize() for w in re.split(r"[\s-]+", lowered_stripped) if w]
        if not words:
            return None
        return "-".join(words) if "-" in clean else " ".join(words)

    @classmethod
    def is_match(
        cls,
        user_city: Optional[str],
        vacancy_city: Optional[str],
        is_remote: bool = False
    ) -> bool:
        """
        Determines whether a vacancy matches the candidate's city requirements:
        1. If vacancy is remote -> always matches.
        2. If user hasn't specified city or wants 'Any' -> always matches.
        3. If vacancy is office-only -> check normalized match.
        """
        # Remote work is location-agnostic
        if is_remote:
            return True

        # Candidate has no city preference
        if not user_city or user_city.strip().lower() in ["", "любой", "все", "любой город", "none"]:
            return True

        norm_user = cls.normalize(user_city)
        if not norm_user or norm_user == "Удаленно":
            return True

        norm_vac = cls.normalize(vacancy_city)
        if not norm_vac:
            # If vacancy didn't specify city, we do not reject it outright
            return False

        if norm_vac == "Удаленно":
            return True

        return norm_user.lower() == norm_vac.lower()
