"""The shape the static site consumes.

The site is meant to be dumb: everything it needs to explain a result must
already be in the JSON, including the sentence justifying a tiebreak.
"""

from __future__ import annotations

import json

from gymrats.core import build_season, tally_month
from gymrats.storage.schema import (
    format_duration,
    month_result_to_dict,
    season_result_to_dict,
)

GENERATED_AT = "2026-07-02T21:15:03-03:00"


def test_duration_is_labelled_for_humans():
    assert format_duration(13301) == "221h41"
    assert format_duration(41) == "0h41"
    assert format_duration(None) is None


def test_published_month_is_json_serialisable(june_tables, participants):
    doc = month_result_to_dict(tally_month("2026-06", june_tables, participants), GENERATED_AT)
    assert json.loads(json.dumps(doc, ensure_ascii=False)) == doc


def test_whole_number_fields_are_ints(june_tables, participants):
    doc = month_result_to_dict(tally_month("2026-06", june_tables, participants), GENERATED_AT)
    values = doc["standings"][0]["values"]

    assert isinstance(values["active_days"], int)
    assert isinstance(values["duration_min"], int)
    assert values["duration_label"] == "221h41"


def test_a_tiebreak_explains_itself(june_tables, participants):
    doc = month_result_to_dict(tally_month("2026-06", june_tables, participants), GENERATED_AT)
    arthur = doc["standings"][0]

    assert arthur["tiebreak"]["resolved_by"] == "distance"
    assert arthur["tiebreak"]["detail"] == (
        "Empate em 4 pontos com Andressa. "
        "Desempatado por maior distância no mês: Arthur 138,61 km, Andressa 121,40 km."
    )


def test_rows_without_a_tie_carry_no_tiebreak(june_tables, participants):
    doc = month_result_to_dict(tally_month("2026-06", june_tables, participants), GENERATED_AT)
    isadora = next(row for row in doc["standings"] if row["name"] == "Isadora")

    assert isadora["tiebreak"] is None


def test_calorie_bonus_is_visible_in_the_published_row(june_tables, participants):
    doc = month_result_to_dict(tally_month("2026-06", june_tables, participants), GENERATED_AT)
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
