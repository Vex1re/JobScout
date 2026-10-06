import re
import logging
from typing import Optional, Dict, Any

from core.config import settings

logger = logging.getLogger(__name__)

# PII regex patterns
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_PATTERN = re.compile(r"(\+7|8)[\s\(-]*\d{3}[\s\)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}")
TOKEN_PATTERN = re.compile(r"(\d{8,12}:[a-zA-Z0-9_-]{20,50})")  # Telegram bot tokens


def filter_pii(text: Optional[str]) -> Optional[str]:
    """Sanitizes text removing potential PII (emails, phone numbers, auth tokens)."""
    if not text:
        return text
    sanitized = EMAIL_PATTERN.sub("[EMAIL_REDACTED]", text)
    sanitized = PHONE_PATTERN.sub("[PHONE_REDACTED]", sanitized)
    sanitized = TOKEN_PATTERN.sub("[TOKEN_REDACTED]", sanitized)
    return sanitized


def _before_send(event: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Hook to strip sensitive PII from Sentry events before transmitting."""
    # Redact message if present
    if "message" in event and isinstance(event["message"], str):
        event["message"] = filter_pii(event["message"])

    # Redact exception values
    if "exception" in event and "values" in event["exception"]:
        for val in event["exception"]["values"]:
            if "value" in val and isinstance(val["value"], str):
                val["value"] = filter_pii(val["value"])

    # Redact breadcrumbs
    if "breadcrumbs" in event and "values" in event["breadcrumbs"]:
        for crumb in event["breadcrumbs"]["values"]:
            if "message" in crumb and isinstance(crumb["message"], str):
                crumb["message"] = filter_pii(crumb["message"])
            if "data" in crumb and isinstance(crumb["data"], dict):
                for k, v in crumb["data"].items():
                    if isinstance(v, str):
                        crumb["data"][k] = filter_pii(v)

    # Redact extra context
    if "extra" in event and isinstance(event["extra"], dict):
        for k, v in event["extra"].items():
            if isinstance(v, str):
                event["extra"][k] = filter_pii(v)

    return event


def _before_breadcrumb(crumb: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Hook to filter breadcrumbs."""
    if "message" in crumb and isinstance(crumb["message"], str):
        crumb["message"] = filter_pii(crumb["message"])
    return crumb


def setup_sentry() -> bool:
    """
    Initializes Sentry SDK if SENTRY_DSN is provided.
    Returns True if initialized, False otherwise.
    """
    if not settings.SENTRY_DSN:
        logger.info("Sentry DSN not provided; error tracking is disabled.")
        return False

    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.SENTRY_ENVIRONMENT,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            before_send=_before_send,
            before_breadcrumb=_before_breadcrumb,
            send_default_pii=False
        )
        logger.info("Sentry successfully initialized for environment: %s", settings.SENTRY_ENVIRONMENT)
        return True
    except Exception as exc:
        logger.warning("Failed to initialize Sentry: %s", exc)
        return False


def capture_exception(
    exc: Exception,
    source: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    extra: Optional[Dict[str, Any]] = None
) -> None:
    """
    Captures an exception to Sentry with source and context tags.
    Safe no-op if Sentry is disabled or not installed.
    """
    if not settings.SENTRY_DSN:
        return

    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            if source:
                scope.set_tag("source", source)
            if tags:
                for k, v in tags.items():
                    scope.set_tag(k, v)
            if extra:
                for k, v in extra.items():
                    scope.set_extra(k, v)
            sentry_sdk.capture_exception(exc)
    except Exception as e:
        logger.debug("Failed to capture exception in Sentry: %s", e)
