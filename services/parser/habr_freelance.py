import re
import html
import datetime
import logging
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple
import xml.etree.ElementTree as ET
import httpx
from bs4 import BeautifulSoup

from services.parser.base import BaseVacanciesParser

logger = logging.getLogger(__name__)


class HabrFreelanceParser(BaseVacanciesParser):
    """
    Parser for Habr Freelance (freelance.habr.com) tasks RSS feed.
    Endpoint: https://freelance.habr.com/tasks.rss?q={query}
    """

    RSS_URL = "https://freelance.habr.com/tasks.rss"
    _service_retired = False

    def __init__(self):
        super().__init__(name="habr_freelance")
        self.is_freelance = True

    async def fetch_vacancies(
        self,
        query: str,
        limit: int = 50,
        remote_only: bool = True,
        page: int = 0,
        city: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if self._service_retired:
            return []

        vacancies: List[Dict[str, Any]] = []

        params = {}
        if query and query.strip():
            params["q"] = query.strip()

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers, follow_redirects=True) as client:
                response = await client.get(self.RSS_URL, params=params)

                if response.status_code == 410:
                    logger.info("Habr Freelance RSS returned status 410 (service retired/closed permanently)")
                    self._service_retired = True
                    return []
                elif response.status_code != 200:
                    logger.warning(f"Habr Freelance RSS returned status {response.status_code}")
                    return []

                items = self._parse_feed_xml(response.content)

                # Pagination simulation for RSS stream
                start_idx = page * limit
                end_idx = start_idx + limit
                paged_items = items[start_idx:end_idx]

                for item in paged_items:
                    title = item.get("title", "")
                    link = item.get("link", "")
                    guid = item.get("guid", "")
                    desc = item.get("description", "")
                    skills = item.get("skills", [])
                    pub_date = item.get("pub_date")

                    task_id_match = re.search(r"/tasks/(\d+)", link) or re.search(r"/tasks/(\d+)", guid)
                    external_id = task_id_match.group(1) if task_id_match else guid or link or title

                    s_min, s_max, currency = self._parse_budget(f"{title} {desc}")

                    vac = self.standardize_vacancy(
                        external_id=str(external_id),
                        title=f"Хабр Фриланс: {title}",
                        company="Заказчик на Хабр Фриланс",
                        url=link,
                        salary_min=s_min,
                        salary_max=s_max,
                        currency=currency,
                        description=desc,
                        requirements=skills if skills else None,
                        is_remote=True,
                        is_freelance=True,
                        city="Удаленно",
                        published_at=pub_date or datetime.datetime.now(datetime.timezone.utc)
                    )
                    vacancies.append(vac)

        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning(f"Network error connecting to Habr Freelance RSS: {exc}")
        except Exception as e:
            logger.error(f"Error fetching tasks from Habr Freelance: {e}", exc_info=True)

        return vacancies

    @classmethod
    def _parse_feed_xml(cls, content: bytes) -> List[Dict[str, Any]]:
        """
        Parses Habr Freelance RSS items and category tags.
        """
        items: List[Dict[str, Any]] = []

        try:
            root = ET.fromstring(content)
            channel = root.find("channel")
            xml_items = channel.findall("item") if channel is not None else root.findall(".//item")

            for item in xml_items:
                raw_title = item.findtext("title") or ""
                title = html.unescape(raw_title).strip()

                raw_link = item.findtext("link") or ""
                link = raw_link.strip()

                raw_guid = item.findtext("guid") or link
                guid = raw_guid.strip()

                raw_desc = item.findtext("description") or ""
                desc_unescaped = html.unescape(raw_desc)
                desc_clean = re.sub(r"<[^>]+>", " ", desc_unescaped).strip()
                desc_clean = re.sub(r"\s+", " ", desc_clean)

                # Skill categories
                categories = [
                    html.unescape(cat.text).strip()
                    for cat in item.findall("category")
                    if cat.text and cat.text.strip()
                ]

                raw_pub_date = item.findtext("pubDate")
                pub_date = None
                if raw_pub_date:
                    try:
                        from email.utils import parsedate_to_datetime
                        pub_date = parsedate_to_datetime(raw_pub_date)
                    except Exception:
                        pub_date = datetime.datetime.now(datetime.timezone.utc)

                items.append({
                    "title": title,
                    "link": link,
                    "guid": guid,
                    "description": desc_clean,
                    "skills": categories,
                    "pub_date": pub_date
                })

            return items
        except ET.ParseError:
            # Fallback using BeautifulSoup
            soup = BeautifulSoup(content, "html.parser")
            for item in soup.find_all("item"):
                title = item.find("title")
                link = item.find("link")
                desc = item.find("description")
                guid = item.find("guid")

                t_text = title.get_text(strip=True) if title else ""
                l_text = link.get_text(strip=True) if link else ""
                d_text = desc.get_text(strip=True) if desc else ""
                g_text = guid.get_text(strip=True) if guid else l_text

                categories = [
                    cat.get_text(strip=True)
                    for cat in item.find_all("category")
                    if cat.get_text(strip=True)
                ]

                items.append({
                    "title": html.unescape(t_text),
                    "link": l_text,
                    "guid": g_text,
                    "description": html.unescape(d_text),
                    "skills": categories,
                    "pub_date": datetime.datetime.now(datetime.timezone.utc)
                })

            return items

    @staticmethod
    def _parse_budget(text: str) -> Tuple[Optional[int], Optional[int], str]:
        if not text:
            return None, None, "RUB"

        decoded = html.unescape(text)
        currency = "RUB"
        if "$" in decoded or "usd" in decoded.lower():
            currency = "USD"
        elif "€" in decoded or "eur" in decoded.lower():
            currency = "EUR"

        # Check for range: 'от 10 000 до 30 000' or '$100 - $300'
        range_match = re.search(
            r"(?:от\s*)?(?:[\$€₽]\s*)?(\d[\d\s]*\d)\s*(?:до|-|—)\s*(?:[\$€₽]\s*)?(\d[\d\s]*\d)\s*(?:руб|₽|\$|eur|usd|&#\d+;)?",
            decoded,
            flags=re.IGNORECASE
        )
        if range_match:
            try:
                min_v = int(re.sub(r"\s+", "", range_match.group(1)))
                max_v = int(re.sub(r"\s+", "", range_match.group(2)))
                if min_v > 0 and max_v > 0:
                    return min_v, max_v, currency
            except ValueError:
                pass

        # Check for single budget amount
        single_match = re.search(
            r"(?:бюджет|цена|стоимость|оплата|budget|price)\s*:?\s*(?:от|до)?\s*(?:[\$€₽]\s*)?(\d[\d\s]*\d)\s*(?:руб|₽|\$|eur|usd|&#\d+;)?",
            decoded,
            flags=re.IGNORECASE
        )
        if single_match:
            try:
                val = int(re.sub(r"\s+", "", single_match.group(1)))
                if val > 0:
                    return val, val, currency
            except ValueError:
                pass

        # Fallback for numbers followed by or preceded by currency symbol
        curr_match = re.search(
            r"(?:[\$€₽]\s*(\d[\d\s]*\d)|(\d[\d\s]*\d)\s*(?:руб|₽|\$|eur|usd|&#\d+;))",
            decoded,
            flags=re.IGNORECASE
        )
        if curr_match:
            try:
                raw_num = curr_match.group(1) or curr_match.group(2)
                val = int(re.sub(r"\s+", "", raw_num))
                if val > 0:
                    return val, val, currency
            except ValueError:
                pass

        return None, None, currency

