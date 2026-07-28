"""Turn the strings GymRats prints into numbers.

Kept in ``core`` on purpose: this is domain knowledge about how the app
formats values, not an OCR concern. The OCR layer hands over ``raw_value``
strings verbatim and never interprets them, so swapping Tesseract for
PaddleOCR cannot change how "1,026.13 quilômetros" is read.

Number convention, per the app: comma is the thousands separator, dot is the
decimal separator.
"""

from __future__ import annotations

import re
import unicodedata

from .models import Modality

__all__ = ["ParseError", "parse_number", "parse_duration_minutes", "parse_value"]


class ParseError(ValueError):
    """Raised when a value string cannot be read.

    Never swallowed: an unparsed value becomes an ``unparsed_value`` issue on
    the review screen so a human decides, rather than a silent zero.
    """


_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_HOURS = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(?:hrs?|horas?)\b", re.IGNORECASE)
_MINUTES = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(?:mins?|minutos?)\b", re.IGNORECASE)


def parse_number(text: str) -> float:
    """Read the first number out of ``text``.

    >>> parse_number("339.75 pontos")
    339.75
    >>> parse_number("14,939 calorias")
    14939.0
    >>> parse_number("1,026.13 quilômetros")
    1026.13
    """
    match = _NUMBER.search(text or "")
    if match is None:
        raise ParseError(f"no number in {text!r}")
    return float(match.group().replace(",", ""))


def parse_duration_minutes(text: str) -> int:
    """Normalise a duration to whole minutes.

    The hours part is optional -- short months come through as just "41 min".

    >>> parse_duration_minutes("221 hr 41 min")
    13301
    >>> parse_duration_minutes("41 min")
    41
    """
    hours = _HOURS.search(text or "")
    minutes = _MINUTES.search(text or "")
    if hours is None and minutes is None:
        raise ParseError(f"no duration in {text!r}")
    total = 0.0
    if hours is not None:
        total += float(hours.group(1).replace(",", "")) * 60
    if minutes is not None:
        total += float(minutes.group(1).replace(",", ""))
    return int(round(total))


def parse_value(modality: Modality, text: str) -> float:
    """Parse a raw leaderboard value according to its modality.

    Returns points, days, calories, kilometres or minutes -- the units the
    rest of the core assumes.
    """
    if modality is Modality.DURATION:
        return float(parse_duration_minutes(text))
    number = parse_number(text)
    if modality is Modality.ACTIVE_DAYS:
        return float(round(number))
    return number


def normalize_name(name: str) -> str:
    """Fold a name for lookup: accents stripped, case flattened, spaces collapsed.

    Used only to *offer* a match to the admin. An unknown name is never
    silently resolved -- see ``roster.resolve``.
    """
    decomposed = unicodedata.normalize("NFKD", name or "")
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(without_accents.casefold().split())
