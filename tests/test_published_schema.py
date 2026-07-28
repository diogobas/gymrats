"""The shape the static site consumes.

The site is meant to be dumb: everything it needs to explain a result must
already be in the JSON, including the sentence justifying a tiebreak.
"""

from __future__ import annotations

import json

import pytest
from gymrats.core import build_season, tally_month
from gymrats.storage.schema import (
    format_duration,
    month_result_to_dict,
    season_result_to_dict,
)

GENERATED_AT = "2026-07-02T21:15:03-03:00"


@pytest.fixture
def june_doc(june_tables, participants):
    """June, tallied and rendered into the shape the static site reads."""
    return month_result_to_dict(
        tally_month("2026-06", june_tables, participants), GENERATED_AT
    )


def test_duration_is_labelled_for_humans():
    assert format_duration(13301) == "221h41"
    assert format_duration(41) == "0h41"
    assert format_duration(None) is None


def test_published_month_is_json_serialisable(june_doc):
    doc = june_doc
    assert json.loads(json.dumps(doc, ensure_ascii=False)) == doc


def test_whole_number_fields_are_ints(june_doc):
    doc = june_doc
    values = doc["standings"][0]["values"]

    assert isinstance(values["active_days"], int)
    assert isinstance(values["duration_min"], int)
    # Arthur, 31 hr 1 min in June.
    assert values["duration_min"] == 1861
    assert values["duration_label"] == "31h01"


def test_a_tiebreak_explains_itself(june_doc):
    doc = june_doc
    arthur = doc["standings"][0]

    assert arthur["tiebreak"]["resolved_by"] == "distance"
    assert arthur["tiebreak"]["detail"] == (
        "Empate em 4 pontos com Andressa. "
        "Desempatado por maior distância no mês: Arthur 107,33 km, Andressa 5,64 km."
    )


def test_rows_without_a_tie_carry_no_tiebreak(june_doc):
    doc = june_doc
    isadora = next(row for row in doc["standings"] if row["name"] == "Isadora")

    assert isadora["tiebreak"] is None


def test_calorie_bonus_is_visible_in_the_published_row(june_doc):
    doc = june_doc
    andressa = next(row for row in doc["standings"] if row["name"] == "Andressa")

    assert andressa["values"]["calories"] == {
        "raw": 10593.0,
        "bonus_applied": True,
        "adjusted": 12711.6,
    }


def test_published_season_separates_imputed_months(june_tables, participants):
    june = tally_month("2026-06", june_tables, participants)
    doc = season_result_to_dict(build_season(2026, [june], june_tables), GENERATED_AT)

    assert doc["months"] == ["2026-06"]
    william = next(row for row in doc["standings"] if row["name"] == "William")
    assert william["by_month"] == {"2026-06": 10}
    assert william["imputed_months"] == []
    assert json.loads(json.dumps(doc, ensure_ascii=False)) == doc
