"""Close a reviewed, complete snapshot without collecting different data."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .collection.client import CollectorError
from .collection.service import bounds
from .core.models import Modality, Period
from .storage.publisher import Publisher
from .storage.repository import Repository
from .storage.schema import month_result_to_dict, tables_from_dict
from .storage.tally_service import TallyService


def close_month(repo, site, month, revision, *, checkout_revision, now=None):
    if not re.fullmatch(r"[a-f0-9]{40}", revision) or revision != checkout_revision:
        raise CollectorError(
            "Os dados mudaram. Reabra a conferência e confirme novamente."
        )
    now = now or datetime.now(UTC)
    first, last = bounds(
        month, today=now.astimezone(ZoneInfo("America/Sao_Paulo")).date()
    )
    if month in repo.months():
        raise CollectorError(
            "Este mês já foi fechado; o fechamento não substitui resultados."
        )
    path = repo.provisional_path(month)
    if not path.is_file():
        raise CollectorError("Não há uma prévia para este mês.")
    doc = json.loads(path.read_text())
    provenance = doc.get("provenance", {})
    if (
        doc.get("month") != month
        or doc.get("provisional") is not True
        or provenance.get("pending_review") is not True
        or provenance.get("partial_day", False) is not False
        or provenance.get("source") != "gymrats_api"
        or provenance.get("challenge_id") != 2504035
        or provenance.get("monthly_start") != first.isoformat()
        or provenance.get("monthly_end") != last.isoformat()
        or provenance.get("annual_start") != f"{first.year}-01-01"
        or provenance.get("annual_end") != last.isoformat()
        or provenance.get("timezone") != "America/Sao_Paulo"
    ):
        raise CollectorError(
            "A prévia não tem o período completo validado para fechamento."
        )
    tables = tables_from_dict(doc)
    expected = {(metric, Period.MONTH) for metric in Modality} | {
        (Modality.DISTANCE, Period.YEAR),
        (Modality.DURATION, Period.YEAR),
    }
    if set(tables.data) != expected or tables.ignore_hustle:
        raise CollectorError("São necessários os sete rankings completos.")
    known = {person.name for person in repo.participants()}
    baseline = None
    for rows in tables.data.values():
        names = {row.name for row in rows}
        if (
            not names
            or len(names) != len(rows)
            or not names <= known
            or (baseline is not None and names != baseline)
            or any(not math.isfinite(row.value) or row.value < 0 for row in rows)
        ):
            raise CollectorError("Confira participantes e valores dos rankings.")
        baseline = names
    tally = TallyService(repo, Publisher(repo, site))
    missing = tally.missing_months(month)
    if missing:
        raise CollectorError("Feche os meses anteriores primeiro: " + ", ".join(missing))
    result = tally.preview(month, tables)
    if result.month.unresolved_ties or result.season.unresolved_ties:
        raise CollectorError("Resolva os empates pendentes antes de fechar o mês.")
    # The reviewed public table must match the source we are about to promote.
    public = json.loads((Path(site) / "months" / f"{month}.json").read_text())
    calculated = month_result_to_dict(result.month, public["generated_at"])
    for field in ("month", "standings", "excluded", "unresolved_ties", "ranked_count"):
        if public.get(field) != calculated[field]:
            raise CollectorError(
                "O resultado publicado diverge da prévia. Atualize e revise."
            )
    reviewed = {
        **provenance,
        "closed_via": "web_admin",
        "reviewed_revision": revision,
        "reviewed_at": now.isoformat(timespec="seconds"),
    }
    reviewed.pop("pending_review", None)
    return tally.commit(month, tables, provenance=reviewed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", required=True)
    parser.add_argument("--reviewed-revision", required=True)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--site", type=Path, default=Path("frontend/public/data"))
    args = parser.parse_args(argv)
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        close_month(
            Repository(args.data),
            args.site,
            args.month,
            args.reviewed_revision,
            checkout_revision=head,
        )
    except CollectorError as exc:
        print("Fechamento cancelado: " + str(exc))
        return 1
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError):
        print("Fechamento cancelado: não foi possível validar os dados revisados.")
        return 1
    print(f"{args.month}: fechado. Publicação será feita após as verificações.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
