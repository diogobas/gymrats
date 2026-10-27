"""Refresh provisional rankings at midnight in Sao Paulo, without closing months."""

from __future__ import annotations

import argparse
import calendar
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .collection.client import CollectorError, save_private
from .collection.service import CollectionService, SessionService
from .core.models import Modality
from .review.assemble import review, to_tables
from .storage.publisher import Publisher
from .storage.repository import Repository
from .storage.schema import draft_from_dict, tables_to_dict
from .storage.tally_service import TallyService

TIMEZONE = "America/Sao_Paulo"


def targets(repo: Repository, now: datetime) -> list[tuple[str, date]]:
    """Catch up unclosed months, using only complete local calendar days."""
    yesterday = now.astimezone(ZoneInfo(TIMEZONE)).date() - timedelta(days=1)
    if yesterday < date(2026, 1, 1):
        return []
    end = min(yesterday, date(2026, 12, 31))
    closed = set(repo.months()) | set(repo.history(2026))
    result = []
    for number in range(1, end.month + 1):
        month = f"2026-{number:02d}"
        if month in closed:
            continue
        cutoff = min(end, date(2026, number, calendar.monthrange(2026, number)[1]))
        if (
            cutoff.day == calendar.monthrange(2026, number)[1]
            and month in repo.complete_provisional_months()
        ):
            continue
        result.append((month, cutoff))
    return result


def _write_all(changes: dict[Path, bytes]) -> None:
    before = {p: p.read_bytes() if p.exists() else None for p in changes}
    try:
        for path, content in changes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    except Exception:
        for path, content in before.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        raise


def refresh(repo, site, private, session, *, now=None) -> list[dict]:
    now = now or datetime.now(UTC)
    planned = targets(repo, now)
    if not planned:
        return []
    with tempfile.TemporaryDirectory() as temporary:
        stage = Path(temporary)
        shutil.copytree(
            repo.root, stage / "data", ignore=shutil.ignore_patterns("inbox", ".local")
        )
        staged = Repository(stage / "data")
        publisher = Publisher(staged, stage / "site")
        service = CollectionService(
            private,
            staged,
            TallyService(staged, publisher),
            session=session,
            timezone=TIMEZONE,
        )
        reports = []
        updated = False
        for month, cutoff in planned:
            old_path = staged.provisional_path(month)
            old = json.loads(old_path.read_text()) if old_path.exists() else None
            if old and old.get("provenance", {}).get("revision", 1) > 1:
                raise CollectorError(
                    "Há correções manuais na prévia; revise antes de automatizar."
                )
            state = service.start(month, True, through=cutoff)
            while service.active:
                time.sleep(0.1)
            state = service.get(state["id"])
            if state["status"] != "complete":
                raise CollectorError(state["error"] or "Coleta incompleta.")
            draft = service.load_draft(state["id"])
            stored = draft_from_dict(draft)
            tables = to_tables(review(stored.tables, staged.participants(), month=month))
            baseline_months = [m for m in staged.published_months() if m <= month]
            if baseline_months:
                baseline = staged.public_tables(baseline_months[-1])
                if set(baseline.names(Modality.HUSTLE)) != set(
                    tables.names(Modality.HUSTLE)
                ):
                    raise CollectorError(
                        "Participantes mudaram; confira cadastro e coleta no admin."
                    )
            preview = service.preview(state["id"], draft["revision"])
            if (
                draft["issues"]
                or preview["month"]["unresolved_ties"]
                or preview["season"]["unresolved_ties"]
            ):
                raise CollectorError(
                    "A atualização exige conferência; a versão publicada foi preservada."
                )
            unchanged = (
                old is not None
                and old.get("provenance", {}).get("automated")
                and old["provenance"]["monthly_end"] == cutoff.isoformat()
                and old["tables"] == tables_to_dict(tables)
            )
            if not unchanged:
                service.commit(
                    state["id"],
                    draft["revision"],
                    preview["preview_token"],
                    True,
                    automated=True,
                )
                updated = True
            reports.append(
                dict(
                    month=month,
                    through=cutoff.isoformat(),
                    pending_review=draft["pending_review"],
                    changed=not unchanged,
                )
            )
        # No official file changes until every planned month has passed validation.
        if updated:
            changes = {}
            for source, destination in (
                (staged.root / "previews", repo.root / "previews"),
                (publisher.out_dir, Path(site)),
            ):
                for path in source.rglob("*.json"):
                    target = destination / path.relative_to(source)
                    content = path.read_bytes()
                    if not target.exists() or target.read_bytes() != content:
                        changes[target] = content
            _write_all(changes)
        return reports


def seal_captures(private: Path, output: Path, key: str) -> None:
    """Keep raw captures as an encrypted artifact; never archive the session file."""
    captures = private / "collections"
    if not captures.is_dir():
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        archive = root / "captures.tar.gz"
        with tarfile.open(archive, "w:gz") as stream:
            stream.add(captures, arcname="collections")
        passphrase = root / "passphrase"
        passphrase.write_text(key, encoding="utf-8")
        passphrase.chmod(0o600)
        completed = subprocess.run(
            [
                "gpg",
                "--batch",
                "--yes",
                "--pinentry-mode",
                "loopback",
                "--passphrase-file",
                str(passphrase),
                "--symmetric",
                "--cipher-algo",
                "AES256",
                "--output",
                str(output),
                str(archive),
            ],
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            raise CollectorError("Não foi possível criptografar as respostas privadas.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--site", type=Path, default=Path("frontend/public/data"))
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args(argv)
    key = os.environ.pop("GYMRATS_ARCHIVE_KEY", "")
    session_json = os.environ.pop("GYMRATS_SESSION_JSON", "")
    try:
        if args.archive and not key:
            raise CollectorError("Configure o secret GYMRATS_ARCHIVE_KEY.")
        if not session_json:
            raise CollectorError(
                "Configure ou renove o secret GYMRATS_SESSION_JSON pelo login local."
            )
        try:
            loaded = json.loads(session_json)
            session = {field: loaded[field] for field in ("token", "signature")}
        except (ValueError, KeyError, TypeError):
            raise CollectorError(
                "Secret de sessão inválido. Renove o login local."
            ) from None
        save_private(args.private / "session.json", session)
        authentication = SessionService(args.private, timezone=TIMEZONE)
        authentication.load()
        reports = refresh(Repository(args.data), args.site, args.private, authentication)
        for item in reports:
            label = "aguardando fechamento" if item["pending_review"] else "em andamento"
            print(f"{item['month']}: dados até {item['through']} ({label}).")
        if not reports:
            print("Sem nova prévia elegível para o clube de 2026.")
        return 0
    except CollectorError as exc:
        print("Atualização não publicada: " + str(exc))
        return 1
    except (OSError, ValueError, KeyError, TypeError):
        # Credentials and remote payloads are never included in error output.
        print("Atualização não publicada. Verifique sessão e rascunhos no admin local.")
        return 1
    finally:
        (args.private / "session.json").unlink(missing_ok=True)
        if args.archive and key:
            try:
                seal_captures(args.private, args.archive, key)
            except (CollectorError, OSError):
                print("Falha ao criptografar respostas; publicação cancelada.")
                return 1


if __name__ == "__main__":
    raise SystemExit(main())
