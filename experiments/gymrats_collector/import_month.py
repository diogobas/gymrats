"""Import a reviewed collection into data/ and regenerate the local static site."""

# ruff: noqa: E402 -- standalone script reuses preview's backend bootstrap.

from __future__ import annotations

import argparse
import calendar
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from collector import LOCAL, CollectorError
from gymrats.report import print_month, print_season
from gymrats.storage.publisher import DEFAULT_OUTPUT, Publisher
from gymrats.storage.repository import Repository
from gymrats.storage.tally_service import TallyService
from preview import collected_tables


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--challenge-id", type=int, required=True)
    parser.add_argument("--local", type=Path, default=LOCAL)
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    parser.add_argument("--out", type=Path, default=ROOT / DEFAULT_OUTPUT)
    parser.add_argument(
        "--commit", action="store_true", help="Save and republish locally."
    )
    parser.add_argument(
        "--replace", action="store_true", help="Replace an existing month."
    )
    parser.add_argument("--allow-incomplete-season", action="store_true")
    args = parser.parse_args(argv)
    try:
        repo = Repository(args.data)
        manifest, tables = collected_tables(
            args.manifest, args.local, repo, challenge_id=args.challenge_id
        )
        month = manifest["month"]
        first = datetime.strptime(month, "%Y-%m").date().replace(day=1)
        last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
        if last >= datetime.now(ZoneInfo("America/Toronto")).date():
            raise CollectorError("Importe somente meses encerrados com este comando.")
        service = TallyService(repo, Publisher(repo, args.out))
        result = service.preview(month, tables)
        print_month(result.month)
        print_season(result.season)
        missing = service.missing_months(month)
        if missing:
            print("Acumulado incompleto. Meses ausentes: " + ", ".join(missing))
        if not args.commit:
            print("Prévia apenas. Para salvar localmente, use --commit.")
            return 0
        if month in repo.published_months() and not args.replace:
            raise CollectorError("Mês existente; confira a prévia e use --replace.")
        if missing and not args.allow_incomplete_season:
            raise CollectorError(
                "Faltam meses anteriores. Use --allow-incomplete-season para importar "
                "somente os meses disponíveis, com aviso no acumulado."
            )
        committed = service.commit(
            month,
            tables,
            provenance={
                "source": "gymrats_api_import",
                "challenge_id": args.challenge_id,
                "monthly_start": first.isoformat(),
                "monthly_end": last.isoformat(),
                "annual_start": first.replace(month=1).isoformat(),
                "annual_end": last.isoformat(),
            },
        )
        print(f"Apuração salva: {committed.month_path}")
        print(f"Site local atualizado: {args.out}. Deploy depende do fluxo Git.")
        return 0
    except (
        CollectorError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
    ) as exc:
        message = str(exc) if isinstance(exc, CollectorError) else "Importação inválida."
        print("Erro: " + message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
