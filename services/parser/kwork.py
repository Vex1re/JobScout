import re
import datetime
import logging
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup
from services.parser.base import BaseVacanciesParser

logger = logging.getLogger(__name__)


class KworkParser(BaseVacanciesParser):
    """
    Parser for Kwork freelance project exchange (kwork.ru/projects).
    Uses official AJAX POST endpoint with XMLHttpRequest headers to parse live projects JSON.
    """

    BASE_URL = "https://kwork.ru"
    PROJECTS_URL = "https://kwork.ru/projects"

    def __init__(self):
        super().__init__(name="kwork")
        self.is_freelance = True

    async def fetch_vacancies(
        self,
        query: str,
        limit: int = 30,
        remote_only: bool = True,
        page: int = 0,
        city: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        post_data = {
            "keyword": query,
            "page": page + 1
        }
        ajax_headers = {
            **self.headers,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://kwork.ru/projects"
        }

        vacancies: List[Dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=ajax_headers, follow_redirects=True) as client:
                response = await client.post(self.PROJECTS_URL, data=post_data, headers=ajax_headers)
                if response.status_code == 200:
                    try:
                        res_json = response.json()
                        wants = []
                        if isinstance(res_json, dict) and "data" in res_json:
                            data_obj = res_json["data"]
                            if isinstance(data_obj, dict) and "wants" in data_obj:
                                wants = data_obj["wants"]
                            elif isinstance(data_obj, list):
                                wants = data_obj

                        for item in wants[:limit]:
                            v_id = str(item.get("id", ""))
                            title = item.get("name", "")
                            if not v_id or not title:
                                continue

                            desc = item.get("description", "")
                            url = f"{self.BASE_URL}/projects/{v_id}"
                            user_data = item.get("user") or {}
                            company = user_data.get("username") or "Заказчик на Kwork"

                            # Parse prices
                            price_limit = item.get("priceLimit")
                            possible_limit = item.get("possiblePriceLimit")
                            salary_min = None
                            salary_max = None
                            try:
                                if price_limit:
                                    salary_min = int(float(str(price_limit).replace(" ", "")))
                                if possible_limit:
                                    salary_max = int(float(str(possible_limit).replace(" ", "")))
                                if salary_min and not salary_max:
                                    salary_max = salary_min
                            except (ValueError, TypeError):
                                salary_min, salary_max = None, None

                            # Parse date
                            date_str = item.get("date_create")
                            published_at = None
                            if date_str:
                                try:
                                    published_at = datetime.datetime.fromisoformat(date_str)
                                except Exception:
                                    published_at = datetime.datetime.now(datetime.timezone.utc)

                            vac = self.standardize_vacancy(
                                external_id=v_id,
                                title=f"💼 Заказ: {title}",
                                company=company,
                                url=url,
                                salary_min=salary_min,
                                salary_max=salary_max,
                                currency="RUB",
                                description=desc,
                                is_remote=True,
                                is_freelance=True,
                                city="Удаленно",
                                published_at=published_at
                            )
                            vacancies.append(vac)

                        if vacancies:
                            return vacancies

                    except Exception as json_err:
                        logger.warning(f"Could not parse Kwork JSON response ({json_err}), attempting HTML fallback...")

                # HTML fallback in case POST doesn't return JSON
                return await self._fetch_via_html(query=query, limit=limit, page=page)

        except Exception as e:
            logger.error(f"Error fetching freelance projects from Kwork: {e}", exc_info=True)

        return vacancies

    async def _fetch_via_html(
        self,
        query: str,
        limit: int = 30,
        page: int = 0
    ) -> List[Dict[str, Any]]:
        """Fallback to GET HTML scraping if AJAX POST is altered."""
        vacancies: List[Dict[str, Any]] = []
        try:
            params = {"keyword": query, "page": page + 1}
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers, follow_redirects=True) as client:
                response = await client.get(self.PROJECTS_URL, params=params)
                if response.status_code != 200:
                    return []
                soup = BeautifulSoup(response.text, "html.parser")
                cards = soup.select(".wants-card, .project-card, [class*='wants-card']")
                for card in cards[:limit]:
                    title_elem = card.select_one(".wants-card__header-title a, .project-card__title a, a[href*='/projects/']")
                    if not title_elem:
                        continue
                    title = title_elem.get_text(strip=True)
                    href = title_elem.get("href", "")
                    url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
                    external_id = href.strip("/").split("/")[-1] if href else title

                    price_elem = card.select_one(".wants-card__header-price, .wants-card__price, .price")
                    price_text = price_elem.get_text(strip=True) if price_elem else ""
                    salary_min, salary_max = self._parse_budget(price_text)

                    desc_elem = card.select_one(".wants-card__description-text, .project-card__desc")
                    desc = desc_elem.get_text(strip=True) if desc_elem else ""

                    vac = self.standardize_vacancy(
                        external_id=external_id,
                        title=f"💼 Заказ: {title}",
                        company="Заказчик на Kwork",
                        url=url,
                        salary_min=salary_min,
                        salary_max=salary_max,
                        currency="RUB",
                        description=desc,
                        is_remote=True,
                        is_freelance=True,
                        city="Удаленно",
                        published_at=datetime.datetime.now(datetime.timezone.utc)
                    )
                    vacancies.append(vac)
        except Exception as exc:
            logger.error(f"Kwork HTML fallback error: {exc}", exc_info=True)

        return vacancies

    @staticmethod
    def _parse_budget(price_text: str) -> tuple[Optional[int], Optional[int]]:
        if not price_text:
            return None, None

        clean = price_text.replace("\xa0", " ").replace(" ", "")
        numbers = re.findall(r"\d+", clean)
        if not numbers:
            return None, None

        if len(numbers) >= 2 and ("до" in price_text.lower() or "-" in price_text):
            try:
                return int(numbers[0]), int(numbers[1])
            except ValueError:
                pass

        if "до" in price_text.lower():
            try:
                return None, int(numbers[-1])
            except ValueError:
                pass

        if "от" in price_text.lower():
            try:
                return int(numbers[0]), None
            except ValueError:
                pass

        try:
            val = int(numbers[0])
            return val, val
        except ValueError:
            return None, None
