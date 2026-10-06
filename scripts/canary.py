import sys
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, List

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.parser.manager import AggregatorManager, SOURCE_LABELS


async def run_canary_checks(query: str = "Python", timeout_sec: float = 15.0) -> List[Dict[str, Any]]:
    """
    Queries each configured aggregator once to verify connectivity and parsing integrity.
    Returns structured list of check outcomes.
    """
    manager = AggregatorManager()
    results = []

    for parser in manager.parsers:
        source_name = parser.name
        label = SOURCE_LABELS.get(source_name, source_name)
        start_time = time.perf_counter()

        try:
            vacancies = await asyncio.wait_for(
                parser.fetch_vacancies(query=query, limit=5, page=0),
                timeout=timeout_sec
            )
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            if isinstance(vacancies, list) and len(vacancies) > 0:
                results.append({
                    "source": source_name,
                    "label": label,
                    "status": "PASS",
                    "count": len(vacancies),
                    "latency_ms": elapsed_ms,
                    "error": None
                })
            else:
                results.append({
                    "source": source_name,
                    "label": label,
                    "status": "EMPTY",
                    "count": 0,
                    "latency_ms": elapsed_ms,
                    "error": "Returned 0 items"
                })

        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            results.append({
                "source": source_name,
                "label": label,
                "status": "FAIL",
                "count": 0,
                "latency_ms": elapsed_ms,
                "error": str(exc)[:80]
            })

    return results


def print_canary_report(results: List[Dict[str, Any]]) -> int:
    header = f"{'Source':<15} | {'Status':<7} | {'Items':<5} | {'Latency':<8} | {'Error / Note'}"
    separator = "-" * len(header)
    print(separator)
    print(" JobScout Bot — Aggregators Canary Health Report")
    print(separator)
    print(header)
    print(separator)

    failed_count = 0
    for r in results:
        status = r["status"]
        if status == "FAIL":
            failed_count += 1
        note = r["error"] or "Healthy"
        print(f"{r['source']:<15} | {status:<7} | {r['count']:<5} | {r['latency_ms']}ms{'':<3} | {note}")

    print(separator)
    passed = sum(1 for r in results if r["status"] == "PASS")
    total = len(results)
    print(f"Summary: {passed}/{total} aggregators healthy.")
    print(separator)
    return failed_count


if __name__ == "__main__":
    test_query = sys.argv[1] if len(sys.argv) > 1 else "Python"
    results = asyncio.run(run_canary_checks(query=test_query))
    exit_code = print_canary_report(results)
    sys.exit(0 if exit_code == 0 else 1)
