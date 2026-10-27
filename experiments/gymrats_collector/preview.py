"""Preview collected rankings through the existing tally, without publishing."""

# ruff: noqa: E402 -- bootstrap the repository backend for standalone execution.

from __future__ import annotations

import argparse
import calendar
import json
import math
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from collector import DEFAULT_CHALLENGE_ID, LOCAL, CollectorError, save_private

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from gymrats.core.models import Entry, Modality, Period, Tables
from gymrats.core.roster import Roster
from gymrats.core.scoring import tally_month
from gymrats.core.season import build_season
from gymrats.report import print_month, print_season
from gymrats.storage.repository import Repository
from gymrats.storage.schema import (
    month_result_to_dict,
    season_result_to_dict,
    tables_to_dict,
)

METRICS = {
    "points": Modality.HUSTLE,
    "days": Modality.ACTIVE_DAYS,
    "calories": Modality.CALORIES,
    "distance": Modality.DISTANCE,
    "duration": Modality.DURATION,
}
REQUIRED = {("month", metric) for metric in METRICS} | {
    ("year", "distance"),
    ("year", "duration"),
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def collected_tables(manifest_path, local, repo):
    manifest = read_json(manifest_path)
    if manifest.get("challenge_id") != DEFAULT_CHALLENGE_ID:
        raise CollectorError("A prévia está limitada ao clube Gymrats 2026!.")
    if manifest.get("status") != "complete":
        raise CollectorError("A coleta está parcial; conclua uma nova coleta.")
    month = manifest["month"]
    first = date.fromisoformat(month + "-01")
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    end = last.isoformat()
    if manifest.get("annual_end_date") != end:
        raise CollectorError("Colete os desempates anuais até o último dia do mês.")
    roster = Roster(repo.participants())
    tables = {}
    ids_by_table = []
    identities = {}
    for item in manifest["responses"]:
        key = (item["period"], item["metric"])
        if key not in REQUIRED:
            raise CollectorError("O manifesto contém uma métrica inesperada.")
        modality, period = METRICS[key[1]], Period(key[0])
        if (modality, period) in tables:
            raise CollectorError("O manifesto contém uma métrica repetida.")
        path = (local / item["file"]).resolve()
        if not path.is_relative_to(local.resolve()):
            raise CollectorError("Resposta fora da pasta local do coletor.")
        capture = read_json(path)
        params = dict(capture["params"])
        expected_start = first if period == Period.MONTH else first.replace(month=1)
        if (
            capture["path"] != f"/challenges/{DEFAULT_CHALLENGE_ID}/rankings"
            or params.get("start_date") != expected_start.isoformat()
            or params.get("end_date") != end
            or params.get("score_by") != key[1]
            or params.get("disable_format") != "true"
            or "limit" in params
        ):
            raise CollectorError(
                "Rota, métrica ou datas da resposta diferem do manifesto."
            )
        response = capture["response"]
        if response.get("status") != "success" or not isinstance(
            response.get("data"), list
        ):
            raise CollectorError("Resposta de ranking sem sucesso confirmado.")
        entries, ids, names = [], set(), set()
        for row in response["data"]:
            account = row["account"]
            name = roster.resolve(account["full_name"]).canonical
            if name is None:
                raise CollectorError("Há um participante sem vínculo no cadastro local.")
            account_id = account["id"]
            if type(account_id) is not int:
                raise CollectorError("ID de participante inválido.")
            if account_id in identities and identities[account_id] != name:
                raise CollectorError("Vínculo de participante difere entre métricas.")
            identities[account_id] = name
            value = float(row["score"])
            if account_id in ids or name in names or not math.isfinite(value):
                raise CollectorError(
                    "Participante duplicado ou valor inválido no ranking."
                )
            ids.add(account_id)
            names.add(name)
            entries.append(Entry(name, value, row.get("rank")))
        if not entries or len(entries) != item["count"]:
            raise CollectorError("Contagem de participantes diverge do manifesto.")
        ids_by_table.append(ids)
        tables[modality, period] = tuple(entries)
    if len(tables) != len(REQUIRED) or any(
        ids != ids_by_table[0] for ids in ids_by_table
    ):
        raise CollectorError("A prévia exige sete rankings com os mesmos participantes.")
    return manifest, Tables.build(tables)


def preview(manifest_path, local, data):
    repo = Repository(data)
    manifest, tables = collected_tables(manifest_path, local, repo)
    month = manifest["month"]
    year = int(month[:4])
    participants = repo.participants()
    result = tally_month(month, tables, participants)
    # Rebuild only through the selected month, using its own annual cutoff.
    detailed = {key for key in repo.months_of(year) if key < month}
    earlier = [
        r
        for r in repo.history_results(year)
        if r.month < month and r.month not in detailed
    ]
    earlier.extend(
        tally_month(key, repo.tables(key), participants) for key in sorted(detailed)
    )
    season = build_season(year, [*earlier, result], tables)
    differences = []
    if month in repo.months():
        previous = repo.tables(month)
        for (modality, period), rows in tables.data.items():
            for row in rows:
                old = previous.value_for(row.name, modality, period)
                if old is not None and Decimal(str(old)).quantize(
                    Decimal(".01")
                ) != Decimal(str(row.value)).quantize(Decimal(".01")):
                    differences.append(
                        {
                            "name": row.name,
                            "metric": modality.value,
                            "period": period.value,
                            "previous": old,
                            "collected": row.value,
                        }
                    )
    present = {r.month for r in [*earlier, result]}
    missing = [
        f"{year}-{m:02d}"
        for m in range(1, int(month[-2:]) + 1)
        if f"{year}-{m:02d}" not in present
    ]
    now = datetime.now(UTC).isoformat()
    output = manifest_path.parent / "preview.json"
    save_private(
        output,
        {
            "schema_version": 1,
            "committed": False,
            "annual_end_date": manifest["annual_end_date"],
            "source_manifest": str(manifest_path.resolve()),
            "missing_months": missing,
            "reference_differences": differences,
            "candidate": {
                "schema_version": 1,
                "month": month,
                "tables": tables_to_dict(tables),
            },
            "month": month_result_to_dict(result, now),
            "season": season_result_to_dict(season, now),
        },
    )
    print_month(result)
    print_season(season)
    print(f"\nCorte anual: {manifest['annual_end_date']}")
    print(f"Diferenças em relação aos dados antigos: {len(differences)} (veja o JSON).")
    if missing:
        print("Acumulado incompleto. Meses ausentes: " + ", ".join(missing))
    print(f"Prévia salva: {output}")
    print("Dados oficiais e publicação preservados. Ex-membros podem faltar na API.")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("month", help="YYYY-MM")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--local", type=Path, default=LOCAL)
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    args = parser.parse_args(argv)
    try:
        manifests = sorted((args.local / "collections").glob("*/manifest.json"))
        chosen = args.manifest
        if chosen is None:
            chosen = next(
                (
                    p
                    for p in reversed(manifests)
                    if read_json(p).get("month") == args.month
                ),
                None,
            )
        if chosen is None:
            raise CollectorError(
                "Coleta ausente. Execute collector.py collect-month YYYY-MM."
            )
        if read_json(chosen).get("month") != args.month:
            raise CollectorError("Mês solicitado difere do manifesto.")
        preview(chosen, args.local, args.data)
    except (
        CollectorError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
    ) as exc:
        message = (
            str(exc)
            if isinstance(exc, CollectorError)
            else "Arquivo inválido ou incompleto para prévia."
        )
        print("Erro: " + message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
