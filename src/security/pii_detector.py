"""
PII detection and anonymisation for user queries and LLM responses.

Detected patterns
-----------------
  EMAIL  — email addresses
  PHONE  — US-format phone numbers (require separators to reduce false positives)
  SSN    — US Social Security Numbers (dashed format, e.g. 123-45-6789)
  IP     — IPv4 addresses (strict octet range validation)

Detected PII values are replaced with typed placeholders so that log entries
and audit trails never contain raw sensitive data.  Example::

    result = detect_and_anonymise("Call me at 555-867-5309 or john@example.com")
    # result.sanitised == "Call me at [PHONE] or [EMAIL]"
    # result.has_pii   == True

Callers should:
  - Log / store ``result.sanitised`` (never ``result.original``).
  - Continue processing with ``result.original`` to preserve query semantics.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)

# Order matters: EMAIL is checked before PHONE to avoid partial-match overlap.
_PII_PATTERNS: list[tuple[str, str]] = [
    ("EMAIL", r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    # US phone: optional country code, optional parentheses, separator-delimited
    ("PHONE", r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"),
    # SSN: dashed format only (123-45-6789) to minimise false positives
    ("SSN", r"\b\d{3}-\d{2}-\d{4}\b"),
    # IPv4: strict per-octet range (0–255)
    (
        "IP",
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
        r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b",
    ),
]

_COMPILED: list[tuple[str, re.Pattern]] = [
    (label, re.compile(pattern)) for label, pattern in _PII_PATTERNS
]


@dataclass
class PIIResult:
    """Outcome of a PII scan on a single text string."""

    original: str
    sanitised: str
    detections: List[str] = field(default_factory=list)

    @property
    def has_pii(self) -> bool:
        """True when one or more PII items were detected."""
        return bool(self.detections)


def detect_and_anonymise(text: str) -> PIIResult:
    """
    Scan *text* for PII patterns and replace each match with a placeholder.

    Returns a :class:`PIIResult` containing:
      - ``original``   — the unchanged input (for query processing)
      - ``sanitised``  — the anonymised version (for logging / storage)
      - ``detections`` — list of label strings for each match found

    The function never raises; on empty input it returns an unchanged result.
    """
    sanitised = text
    detections: list[str] = []

    for label, pattern in _COMPILED:
        matches = pattern.findall(sanitised)
        if matches:
            detections.extend([label] * len(matches))
            sanitised = pattern.sub(f"[{label}]", sanitised)

    if detections:
        logger.info(
            "[PIIDetector] %d PII item(s) detected (%s). "
            "Original query will NOT be logged.",
            len(detections),
            ", ".join(sorted(set(detections))),
        )

    return PIIResult(original=text, sanitised=sanitised, detections=detections)
