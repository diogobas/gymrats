"""Reading the strings GymRats prints."""

from __future__ import annotations

import pytest
from gymrats.core import (
    Modality,
    ParseError,
    parse_duration_minutes,
    parse_number,
    parse_value,
)
from gymrats.core.values import normalize_name


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("339.75 pontos", 339.75),
        ("24 dias ativo", 24.0),
        ("14,939 calorias", 14939.0),
        ("138.61 quilômetros", 138.61),
        ("1,026.13 quilômetros", 1026.13),
        ("8,120 calorias", 8120.0),
        ("0 pontos", 0.0),
    ],
)
def test_parse_number_reads_app_formats(text, expected):
    assert parse_number(text) == expected


def test_comma_is_thousands_and_dot_is_decimal():
    # The one that would silently ruin a season if it flipped.
    assert parse_number("1,026.13") == 1026.13
    assert parse_number("1,026") == 1026.0


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("221 hr 41 min", 13301),
        ("41 min", 41),
        ("1 hr", 60),
        ("1,026 hr 5 min", 61565),
        ("221 horas 41 minutos", 13301),
    ],
)
def test_duration_normalises_to_minutes(text, expected):
    assert parse_duration_minutes(text) == expected


@pytest.mark.parametrize("text", ["", "pontos", "sem número aqui"])
def test_unreadable_values_raise_rather_than_defaulting_to_zero(text):
    with pytest.raises(ParseError):
        parse_number(text)


def test_unreadable_duration_raises():
    with pytest.raises(ParseError):
        parse_duration_minutes("221")


def test_parse_value_dispatches_on_modality():
    assert parse_value(Modality.HUSTLE, "339.75 pontos") == 339.75
    assert parse_value(Modality.ACTIVE_DAYS, "24 dias ativo") == 24
    assert parse_value(Modality.CALORIES, "14,939 calorias") == 14939.0
    assert parse_value(Modality.DISTANCE, "138.61 quilômetros") == 138.61
    assert parse_value(Modality.DURATION, "221 hr 41 min") == 13301.0


def test_normalize_name_folds_accents_and_case():
    assert normalize_name("Túlio") == normalize_name("tulio")
    assert normalize_name("Laíssa") == normalize_name("LAISSA")
    assert normalize_name("  Arthur   Pereira ") == "arthur pereira"
