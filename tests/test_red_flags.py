import pytest
from services.resume_analyzer.red_flags import RedFlagScanner


def test_clean_vacancy():
    title = "Python Backend Developer"
    company = "Yandex"
    desc = "Ищем Middle Python разработчика. Требования: FastAPI, PostgreSQL, Docker, Git. Белая зарплата, ДМС, удаленка."
    
    result = RedFlagScanner.scan(title=title, description=desc, company=company)
    assert result["risk_level"] == "safe"
    assert result["is_clean"] is True
    assert result["safety_score"] == 100
    assert len(result["red_flags"]) == 0


def test_deposit_scam_blocked():
    title = "Оператор ПК / Наборщик текста"
    company = "ИП Иванов"
    desc = "Работа на дому. Набор текста с рукописных сканов. Для получения материалов требуется внести страховой взнос 1500 руб."
    
    result = RedFlagScanner.scan(title=title, description=desc, company=company)
    assert result["risk_level"] == "blocked"
    assert result["is_clean"] is False
    assert result["safety_score"] == 0
    assert any("страхового взноса" in rf for rf in result["red_flags"])


def test_dropper_scam_blocked():
    title = "Менеджер финансовых транзакций"
    company = "Global Pay"
    desc = "Прием и обработка платежей на свою личную карту, быстрый процент, дропперство, вывод средств."
    
    result = RedFlagScanner.scan(title=title, description=desc, company=company)
    assert result["risk_level"] == "blocked"
    assert result["safety_score"] == 0


def test_warning_toxic_conditions():
    title = "Junior Python Разработчик"
    company = "Стартап"
    desc = "Испытательный срок без оплаты 3 месяца. Серая зарплата в конверте. Работа в режиме 24/7."
    
    result = RedFlagScanner.scan(title=title, description=desc, company=company)
    assert result["risk_level"] == "warning"
    assert len(result["red_flags"]) >= 2
    assert result["safety_score"] < 100
