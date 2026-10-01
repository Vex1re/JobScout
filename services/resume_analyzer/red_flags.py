import re
from typing import List, Tuple, Dict, Any


class RedFlagScanner:
    """
    Scanner for detecting scam vacancies, fraudulent offers,
    unrealistic promises, and toxic work conditions.
    """

    # Critical scam patterns that result in immediate 'blocked' status
    SCAM_PATTERNS = [
        (r"(страхов(ой|ую)\s+(взнос|депозит|платеж))", "Требование страхового взноса или депозита"),
        (r"(залог\s+(за\s+материал|перед\s+работ|для\s+гарантии))", "Требование денежного залога"),
        (r"(оплат(а|ить)\s+(за\s+обучени|курс|материал)\s+(для|перед)\s+(трудоустройств|работ))", "Требование платного обучения перед началом работы"),
        (r"(набор\s+текста\s+(с\s+предоплат|залог|гарантийный\s+взнос))", "Классическая схема мошенничества с набором текста"),
        (r"(дроп(пер|ерств|ы)|обработк(а|е)\s+платежей\s+на\s+(сво(ю|и)|личн(ую|ые))\s+карт)", "Признаки финансового дропперства и отмывания средств"),
        (r"(транзитн(ый|ые)\s+счет|обнал|вывод\s+средств\s+через\s+вас)", "Предложение сомнительных финансовых операций / обнала"),
        (r"(даркнет|закладк|курьер\s+легких\s+веществ|доставка\s+без\s+досмотра)", "Нелегальная деятельность"),
        (r"(схем(а|ы)\s+заработка\s+в\s+казино|ставк(и|ах)\s+на\s+спорт|криптобот\s+100%\s+доход)", "Схемы обмана и финансовые пирамиды"),
        (r"(сетевой\s+маркетинг|tiens|тяньши|qnet|herbalife|вход\s+в\s+бизнес\s+от\s+\d+)", "Сетевой маркетинг / финансовая пирамида"),
    ]

    # Warning patterns: suspicious or toxic work conditions
    WARNING_PATTERNS = [
        (r"(испытательн(ый|ого)\s+срок(а)?\s+без\s+оплат)", "⚠️ Неоплачиваемый испытательный срок"),
        (r"(без\s+(официального\s+)?оформлени|без\s+тк\s+рф|оформление\s+когда-нибудь)", "⚠️ Работа без официального оформления"),
        (r"(сер(ая|ую)\s+зарплат|зп\s+в\s+конверт|оклад\s+минималк)", "⚠️ Серая заработная плата"),
        (r"(работа\s+(в\s+режиме\s+)?24/7|ненормированн(ый|о)\s+без\s+(компенсаци|доплат))", "⚠️ Риск переработок: указан режим 24/7 без компенсации"),
        (r"(штраф(ы|ов)\s+за\s+(опоздани|все|любые\s+ошибк))", "⚠️ Системы необоснованных денежных штрафов"),
        (r"(здесь\s+не\s+отвеча(ю|ем),\s+пишите\s+только\s+в\s+(тг|телеграм|telegram|tg|whatsapp))", "⚠️ Перевод общения на сторонние сомнительные каналы"),
        (r"(опыт\s+не\s+требуется.{0,50}(300\s?000|400\s?000|500\s?000|10\s?000\$))", "⚠️ Нереалистично высокая зарплата при отсутствии требований к опыту"),
    ]

    @classmethod
    def scan(cls, title: str, description: str, company: str = "") -> Dict[str, Any]:
        """
        Scans job posting for red flags and returns assessment.
        
        Returns:
            dict with:
                - risk_level: 'safe' | 'warning' | 'blocked'
                - red_flags: List[str] of detected red flag descriptions
                - is_clean: bool
                - score: int (0 to 100 safety score)
        """
        full_text = f"{title}\n{company}\n{description}".lower()
        red_flags: List[str] = []
        is_blocked = False

        # 1. Check critical scam patterns
        for pattern, message in cls.SCAM_PATTERNS:
            if re.search(pattern, full_text, flags=re.IGNORECASE):
                red_flags.append(f"⛔ {message}")
                is_blocked = True

        # 2. Check warning patterns
        for pattern, message in cls.WARNING_PATTERNS:
            if re.search(pattern, full_text, flags=re.IGNORECASE):
                red_flags.append(message)

        # 3. Check for empty company or fishy descriptions
        if not company or company.strip().lower() in ["не указана", "частное лицо", "анонимный работодатель"]:
            if any(k in full_text for k in ["деньги сразу", "быстрый доход", "оплата каждый день"]):
                red_flags.append("⚠️ Анонимный наниматель с обещанием быстрых выплат")

        # Determine risk level and safety score
        if is_blocked:
            risk_level = "blocked"
            safety_score = 0
        elif red_flags:
            risk_level = "warning"
            safety_score = max(30, 100 - len(red_flags) * 25)
        else:
            risk_level = "safe"
            safety_score = 100

        return {
            "risk_level": risk_level,
            "red_flags": red_flags,
            "is_clean": len(red_flags) == 0,
            "safety_score": safety_score
        }
