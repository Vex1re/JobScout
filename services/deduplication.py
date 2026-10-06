import hashlib
import re
from typing import List, Dict, Any, Optional, Tuple


def normalize_company_name(company: Optional[str]) -> str:
    """Normalizes company name by stripping legal forms and punctuation."""
    if not company:
        return "unknown"
    clean = re.sub(
        r'\b(ооо|зао|пао|ип|акционерное общество|llc|inc|ltd|gmbh|corp|corporation)\b',
        '',
        company,
        flags=re.IGNORECASE
    )
    clean = re.sub(r'[\"\',.:;\-_()/\\]', ' ', clean)
    words = clean.strip().lower().split()
    return " ".join(words) if words else "unknown"


def normalize_title(title: Optional[str]) -> str:
    """Normalizes vacancy title."""
    if not title:
        return "unknown"
    clean = re.sub(r'[\"\',.:;\-_()/\\]', ' ', title)
    words = clean.strip().lower().split()
    return " ".join(words) if words else "unknown"


def get_salary_bucket(salary_from: Optional[int], salary_to: Optional[int], currency: Optional[str] = "RUB") -> str:
    """Computes salary bucket for deduplication clustering."""
    from services.parser.normalizer import CurrencyNormalizer
    rub_from = CurrencyNormalizer.normalize_to_rub(salary_from, currency)
    rub_to = CurrencyNormalizer.normalize_to_rub(salary_to, currency)

    if rub_from is None and rub_to is None:
        return "none"
    avg = (rub_from or rub_to or 0) if (rub_from is None or rub_to is None) else (rub_from + rub_to) // 2
    # Bucket into 30k intervals
    bucket = (avg // 30000) * 30000
    return f"{bucket // 1000}k"


def generate_canonical_id(
    company: Optional[str],
    title: Optional[str],
    city: Optional[str] = None,
    salary_from: Optional[int] = None,
    salary_to: Optional[int] = None,
    currency: Optional[str] = "RUB"
) -> str:
    """
    Generates a deterministic 16-character canonical hash for cross-source vacancy deduplication.
    canonical_id = hash(norm_company + norm_title + norm_city + salary_bucket)
    """
    from services.parser.normalizer import CityNormalizer
    comp_norm = normalize_company_name(company)
    title_norm = normalize_title(title)
    city_norm = (CityNormalizer.normalize(city) or "any").lower()
    sal_bucket = get_salary_bucket(salary_from, salary_to, currency)

    key_str = f"{comp_norm}:{title_norm}:{city_norm}:{sal_bucket}"
    return hashlib.sha256(key_str.encode("utf-8")).hexdigest()[:16]


def compute_simhash(text: str, hash_bits: int = 64) -> int:
    """Computes a 64-bit SimHash fingerprint for text near-duplicate detection."""
    if not text:
        return 0

    tokens = re.findall(r'\b[a-zA-Zа-яА-Я0-9_]{3,}\b', text.lower())
    if not tokens:
        return 0

    # Include unigrams and bigram shingles for robust similarity
    shingles = list(tokens)
    for i in range(len(tokens) - 1):
        shingles.append(f"{tokens[i]}_{tokens[i+1]}")

    v = [0] * hash_bits
    for token in shingles:
        token_hash = int(hashlib.md5(token.encode('utf-8')).hexdigest()[:16], 16)
        for i in range(hash_bits):
            bit = (token_hash >> i) & 1
            v[i] += 1 if bit else -1

    fingerprint = 0
    for i in range(hash_bits):
        if v[i] > 0:
            fingerprint |= (1 << i)

    return fingerprint


def simhash_distance(h1: int, h2: int) -> int:
    """Computes Hamming distance between two SimHash fingerprints."""
    return bin(h1 ^ h2).count("1")


def deduplicate_vacancies(
    vacancies: List[Dict[str, Any]],
    simhash_threshold: int = 3
) -> List[Dict[str, Any]]:
    """
    Deduplicates a list of vacancies:
    1. Exact canonical_id matches are collapsed into a single record.
    2. Merges sources list and url dictionary.
    3. Retains most complete description and highest salary.
    """
    collapsed: Dict[str, Dict[str, Any]] = {}

    for vac in vacancies:
        cid = vac.get("canonical_id")
        if not cid:
            cid = generate_canonical_id(
                company=vac.get("company"),
                title=vac.get("title"),
                city=vac.get("city"),
                salary_from=vac.get("salary_min") or vac.get("salary_from"),
                salary_to=vac.get("salary_max") or vac.get("salary_to"),
                currency=vac.get("currency")
            )
            vac["canonical_id"] = cid

        if cid not in collapsed:
            record = dict(vac)
            record["sources"] = [vac.get("source", "unknown")]
            record["source_urls"] = {vac.get("source", "unknown"): vac.get("url", "")}
            collapsed[cid] = record
        else:
            existing = collapsed[cid]
            src = vac.get("source", "unknown")
            if src not in existing["sources"]:
                existing["sources"].append(src)
            existing["source_urls"][src] = vac.get("url", "")

            # Keep longest description
            if len(vac.get("description", "")) > len(existing.get("description", "")):
                existing["description"] = vac["description"]
                existing["snippet"] = vac.get("snippet") or existing.get("snippet")

            # Keep richer salary: expand range
            if vac.get("salary_max"):
                cur_max = existing.get("salary_max") or 0
                existing["salary_max"] = max(cur_max, vac["salary_max"])
                existing["salary_to"] = existing["salary_max"]

            if vac.get("salary_min"):
                if not existing.get("salary_min"):
                    existing["salary_min"] = vac["salary_min"]
                else:
                    existing["salary_min"] = min(existing["salary_min"], vac["salary_min"])
                existing["salary_from"] = existing["salary_min"]

    return list(collapsed.values())
