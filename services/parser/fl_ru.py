import re
import html
import datetime
import logging
from typing import List, Dict, Any, Optional, Tuple
import xml.etree.ElementTree as ET
import httpx
from bs4 import BeautifulSoup

from services.parser.base import BaseVacanciesParser

logger = logging.getLogger(__name__)


class FLRuParser(BaseVacanciesParser):
    """
    Parser for FL.ru freelance platform using RSS feeds.
    Feeds:
    - category=5: Programming / Development
    - category=2: Websites / Web Development
    """

    FEEDS = [
        "https://www.fl.ru/rss/all.xml?category=5",
        "https://www.fl.ru/rss/all.xml?category=2"
    ]

    def __init__(self):
        super().__init__(name="fl_ru")
        self.is_freelance = True

    async def fetch_vacancies(
        self,
        query: str,
        limit: int = 50,
        remote_only: bool = True,
        page: int = 0,
        city: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        vacancies: List[Dict[str, Any]] = []
        raw_items: List[Dict[str, Any]] = []
        seen_links = set()

        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers, follow_redirects=True) as client:
            for feed_url in self.FEEDS:
                try:
                    response = await client.get(feed_url)
                    if response.status_code != 200:
                        logger.warning(f"FL.ru feed returned status {response.status_code} for {feed_url}")
                        continue

                    feed_items = self._parse_rss_content(response.content)
                    for item in feed_items:
                        link = item.get("link", "")
                        if link and link not in seen_links:
                            seen_links.add(link)
                            raw_items.append(item)
                except (httpx.ConnectError, httpx.TimeoutException) as exc:
                    logger.warning(f"Network error fetching FL.ru feed {feed_url}: {exc}")
                except Exception as exc:
                    logger.error(f"Error fetching FL.ru feed {feed_url}: {exc}", exc_info=True)

        if not raw_items:
            return []

        # Filter by search query if provided
        filtered_items = self._filter_by_query(raw_items, query)

        # Pagination simulation for RSS stream
        start_idx = page * limit
        end_idx = start_idx + limit
        paged_items = filtered_items[start_idx:end_idx]

        for item in paged_items:
            try:
                title = item.get("title", "")
                link = item.get("link", "")
                desc = item.get("description", "")
                guid = item.get("guid", "")
                pub_date = item.get("pub_date")

                # Extract external id
                id_match = re.search(r"/projects/(\d+)", link) or re.search(r"/projects/(\d+)", guid)
                external_id = id_match.group(1) if id_match else guid or link or title

                # Parse budget & currency
                s_min, s_max, currency = self._parse_budget(f"{title} {desc}")

                # Format clean title
                clean_title = re.sub(r"\s*\(?(?:Бюджет|Цена)?:?\s*[\d\s]+(?:&#\d+;|руб|₽|\$|usd|eur|€)?\)?", "", title, flags=re.IGNORECASE).strip()
                if not clean_title:
                    clean_title = title

                vac = self.standardize_vacancy(
                    external_id=str(external_id),
                    title=f"FL.ru: {clean_title}",
                    company="Заказчик на FL.ru",
                    url=link,
                    salary_min=s_min,
                    salary_max=s_max,
                    currency=currency,
                    description=desc,
                    is_remote=True,
                    is_freelance=True,
                    city="Удаленно",
                    published_at=pub_date or datetime.datetime.now(datetime.timezone.utc)
                )
                vacancies.append(vac)
            except Exception as e:
                logger.error(f"Error standardizing FL.ru item: {e}", exc_info=True)

        return vacancies

    @classmethod
    def _parse_rss_content(cls, content: bytes) -> List[Dict[str, Any]]:
        """
        Parses RSS XML using xml.etree.ElementTree with BeautifulSoup fallback.
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
                # Strip HTML tags
                desc_clean = re.sub(r"<[^>]+>", " ", desc_unescaped).strip()
                desc_clean = re.sub(r"\s+", " ", desc_clean)

                raw_pub_date = item.findtext("pubDate")
                pub_date = None
                if raw_pub_date:
                    try:
                        # RFC 822 / 2822: e.g. 'Thu, 01 Oct 2026 21:36:13 GMT'
                        from email.utils import parsedate_to_datetime
                        pub_date = parsedate_to_datetime(raw_pub_date)
                    except Exception:
                        pub_date = datetime.datetime.now(datetime.timezone.utc)

                items.append({
                    "title": title,
                    "link": link,
                    "guid": guid,
                    "description": desc_clean,
                    "pub_date": pub_date
                })

            return items
        except ET.ParseError:
            # Fallback to BeautifulSoup if XML is ill-formed
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

                items.append({
                    "title": html.unescape(t_text),
                    "link": l_text,
                    "guid": g_text,
                    "description": html.unescape(d_text),
                    "pub_date": datetime.datetime.now(datetime.timezone.utc)
                })

            return items

    @classmethod
    def _filter_by_query(cls, items: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        if not query or not query.strip():
            return items

        keywords = [
            w.lower() for w in re.findall(r"[\w+#]+", query)
            if len(w) >= 2 and w.lower() not in {"junior", "middle", "senior", "lead", "стажер", "вакансия", "работа"}
        ]

        if not keywords:
            return items

        filtered = []
        for it in items:
            searchable = f"{it.get('title', '')} {it.get('description', '')}".lower()
            if any(k in searchable for k in keywords):
                filtered.append(it)

        # If strict keyword matching gave results, return them; otherwise don't drop everything
        return filtered if filtered else items

    @staticmethod
    def _parse_budget(text: str) -> Tuple[Optional[int], Optional[int], str]:
        """
        Parses budget/price and currency from freelance project text.
        """
        if not text:
            return None, None, "RUB"

        decoded = html.unescape(text)
        currency = "RUB"
        if "$" in decoded or "usd" in decoded.lower():
            currency = "USD"
        elif "€" in decoded or "eur" in decoded.lower():
            currency = "EUR"

        # Check for range: 'от 10 000 до 30 000' or '10 000 - 30 000' or '$100 - $300'
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

        # Check for single budget: '(Бюджет: 30 000 руб)' or '(Budget: $200)'
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
