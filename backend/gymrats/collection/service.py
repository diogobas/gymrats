"""Private session, durable collection jobs and revision-checked review.

Raw captures are immutable; corrections live in a separate revisioned file.
Only explicit allowlists cross the local HTTP boundary.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import math
import re
import threading
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import monotonic, sleep
from zoneinfo import ZoneInfo

from ..core.models import Modality, Period
from ..review.assemble import review, to_tables
from ..review.models import DraftRow, DraftTable
from ..storage.schema import draft_from_dict, draft_to_dict, tally_result_to_dict
from .client import (
    APP_VERSION,
    DEFAULT_CHALLENGE_ID,
    CollectorError,
    redact,
    request_json,
    save_private,
)

METRICS = dict(
    points=Modality.HUSTLE,
    days=Modality.ACTIVE_DAYS,
    calories=Modality.CALORIES,
    distance=Modality.DISTANCE,
    duration=Modality.DURATION,
)
PLAN = [("month", metric) for metric in METRICS] + [
    ("year", "distance"),
    ("year", "duration"),
]


def bounds(month, *, closed=True, today=None):
    try:
        first = date.fromisoformat(month + "-01")
        if first.year != 2026 or first.strftime("%Y-%m") != month:
            raise ValueError
    except (TypeError, ValueError):
        raise CollectorError("Escolha um mês de 2026 no formato YYYY-MM.") from None
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    if closed and last >= (today or datetime.now(ZoneInfo("America/Toronto")).date()):
        raise CollectorError("O mês ainda não terminou.")
    return first, last


_NUMBER = r"\d+(?:,\d{3})*(?:\.\d+)?"
_UNITS = {
    Modality.HUSTLE: r"(?:pontos?|points?)?",
    Modality.ACTIVE_DAYS: r"(?:dias?|days?)?",
    Modality.CALORIES: r"(?:kcal|calorias?|calories?)?",
    Modality.DISTANCE: r"(?:km|quilômetros?|kilometers?)?",
}


def valid_raw(modality, raw):
    if modality == Modality.DURATION:
        pattern = (
            rf"(?:{_NUMBER}\s*(?:hrs?|horas?)\s*)?"
            rf"(?:{_NUMBER}\s*(?:mins?|minutos?))?"
        )
        return bool(raw.strip()) and re.fullmatch(pattern, raw.strip(), re.I) is not None
    return re.fullmatch(rf"{_NUMBER}\s*{_UNITS[modality]}", raw.strip(), re.I) is not None


def local_today():
    return datetime.now(ZoneInfo("America/Toronto")).date()


def collection_window(month, provisional=False, *, today=None):
    today = today or local_today()
    if not provisional:
        return bounds(month, today=today)
    first, _ = bounds(month, closed=False)
    if first != today.replace(day=1):
        raise CollectorError("A prévia parcial é permitida somente para o mês vigente.")
    end = today - timedelta(days=1)
    if end < first:
        raise CollectorError("O mês vigente ainda não tem um dia completo para coletar.")
    return first, end


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class SessionService:
    def __init__(self, root, transport=None):
        self.root = Path(root)
        self.transport = transport or request_json
        self.pending = None
        self.lock = threading.RLock()

    def request(self, path, session, **kwargs):
        result = self.transport(
            path,
            session=session,
            version=APP_VERSION,
            timezone="America/Toronto",
            **kwargs,
        )
        if not isinstance(result, dict) or result.get("status") != "success":
            raise CollectorError("A API não confirmou sucesso.")
        return result.get("data")

    def load(self):
        try:
            session = read(self.root / "session.json")
            if not isinstance(session, dict) or not all(
                isinstance(session.get(k), str)
                and session[k]
                and not any(c.isspace() for c in session[k])
                for k in ("token", "signature")
            ):
                raise ValueError
            return session
        except (OSError, ValueError, TypeError):
            raise CollectorError("Conecte sua conta GymRats.") from None

    def validate(self, session):
        account = self.request("/account", session)
        groups = self.request("/challenges", session)
        if not isinstance(account, dict) or type(account.get("id")) is not int:
            raise CollectorError("Não foi possível validar a conta.")
        if not isinstance(groups, list) or not any(
            g.get("id") == DEFAULT_CHALLENGE_ID and g.get("joined_at")
            for g in groups
            if isinstance(g, dict)
        ):
            raise CollectorError("Esta conta não tem acesso ao clube Gymrats 2026!.")
        return {
            "connected": True,
            "account": {"id": account["id"], "name": account.get("full_name", "")},
            "club": "Gymrats 2026!",
            "challenge_id": DEFAULT_CHALLENGE_ID,
        }

    def status(self):
        with self.lock:
            try:
                return self.validate(self.load())
            except CollectorError as exc:
                return {
                    "connected": False,
                    "message": str(exc),
                    "code_pending": self.pending is not None,
                }

    def request_code(self, email):
        if "@" not in email or any(c.isspace() for c in email):
            raise CollectorError("Informe o e-mail vinculado à conta existente.")
        with self.lock:
            session = {"signature": str(uuid.uuid4())}
            data = self.request(
                "/accounts/email_confirmation",
                session,
                credentials={"email": email, "locale": "en"},
            )
            if (
                not isinstance(data, dict)
                or not isinstance(data.get("nonce"), str)
                or not data["nonce"]
            ):
                raise CollectorError("Não foi possível solicitar o código.")
            self.pending = (session, data["nonce"], monotonic())
            return {"code_pending": True}

    def verify(self, code):
        with self.lock:
            if not self.pending or monotonic() - self.pending[2] > 600:
                raise CollectorError("Solicite um novo código.")
            if not code or len(code) > 128 or any(c.isspace() for c in code):
                raise CollectorError("Código inválido.")
            session, nonce, _ = self.pending
            data = self.request(
                "/accounts/sign_in",
                session,
                credentials={
                    "token": code,
                    "nonce": nonce,
                    "region_code": "CA",
                    "language_locale": "en",
                },
            )
            token = data.get("token") if isinstance(data, dict) else None
            if not isinstance(token, str) or not token or any(c.isspace() for c in token):
                raise CollectorError("Código recusado. Solicite outro código.")
            candidate = {**session, "token": token}
            status = self.validate(candidate)
            save_private(self.root / "session.json", candidate)
            self.pending = None
            return status

    def disconnect(self):
        with self.lock:
            (self.root / "session.json").unlink(missing_ok=True)
            self.pending = None
        return {"connected": False}


class CollectionService:
    def __init__(self, root, repo, tally, session=None):
        self.root = Path(root)
        self.repo, self.tally = repo, tally
        self.session = session or SessionService(root)
        self.lock = threading.RLock()
        self.active = None
        for path in (self.root / "collections").glob("*/manifest.json"):
            if not re.fullmatch(r"[a-f0-9]{32}", path.parent.name):
                continue  # Standalone research captures keep their original layout.
            manifest = read(path)
            if manifest["status"] == "running":
                manifest.update(
                    status="interrupted", error="Coleta interrompida pelo reinício."
                )
                save_private(path, manifest)

    def folder(self, run):
        if not re.fullmatch(r"[a-f0-9]{32}", run):
            raise CollectorError("Execução inválida.")
        folder = self.root / "collections" / run
        if not (folder / "manifest.json").is_file():
            raise CollectorError("Execução não encontrada.")
        return folder

    def get(self, run):
        doc = read(self.folder(run) / "manifest.json")
        return {
            **{
                k: doc[k]
                for k in (
                    "id",
                    "month",
                    "annual_end_date",
                    "status",
                    "completed",
                    "error",
                    "created_at",
                )
            },
            "provisional": doc.get("provisional", False),
        }

    def list(self):
        runs = [
            self.get(p.parent.name)
            for p in (self.root / "collections").glob("*/manifest.json")
            if re.fullmatch(r"[a-f0-9]{32}", p.parent.name)
        ]
        return sorted(runs, key=lambda run: run["created_at"], reverse=True)

    def start(self, month, provisional=False):
        first, last = collection_window(month, provisional)
        with self.lock:
            if self.active:
                raise CollectorError("Já existe uma coleta em andamento.")
            session = self.session.load()
            run = uuid.uuid4().hex
            manifest = dict(
                id=run,
                month=month,
                annual_end_date=last.isoformat(),
                challenge_id=DEFAULT_CHALLENGE_ID,
                provisional=provisional,
                status="running",
                completed=0,
                responses=[],
                error=None,
                created_at=datetime.now(UTC).isoformat(),
            )
            save_private(self.root / "collections" / run / "manifest.json", manifest)
            self.active = run
            threading.Thread(
                target=self.collect, args=(run, session, first, last), daemon=True
            ).start()
            return self.get(run)

    def collect(self, run, session, first, last):
        folder = self.folder(run)
        manifest = read(folder / "manifest.json")
        expected, identities = None, {}
        try:
            self.session.validate(session)
            for index, (period, metric) in enumerate(PLAN):
                if index:
                    sleep(0.5)
                params = [
                    ("disable_format", "true"),
                    ("score_by", metric),
                    (
                        "start_date",
                        (
                            first if period == "month" else first.replace(month=1)
                        ).isoformat(),
                    ),
                    ("end_date", last.isoformat()),
                ]
                path = f"/challenges/{DEFAULT_CHALLENGE_ID}/rankings"
                data = self.session.request(path, session, params=params)
                file = f"{period}-{metric}.json"
                save_private(
                    folder / file,
                    {
                        "path": path,
                        "params": params,
                        "response": {
                            "status": "success",
                            "data": redact(data, (session["token"],)),
                        },
                    },
                )
                manifest["responses"].append(
                    dict(period=period, metric=metric, file=file)
                )
                save_private(folder / "manifest.json", manifest)
                ids = self.validate_rows(data, identities)
                if expected is not None and ids != expected:
                    raise CollectorError("Participantes diferem entre os sete rankings.")
                expected = ids
                manifest["completed"] += 1
                save_private(folder / "manifest.json", manifest)
            manifest["status"] = "complete"
        except CollectorError as exc:
            manifest.update(status="partial", error=str(exc))
        except Exception:
            manifest.update(
                status="partial", error="Resposta inválida ou falha ao salvar a coleta."
            )
        finally:
            with self.lock:
                try:
                    save_private(folder / "manifest.json", manifest)
                finally:
                    self.active = None

    @staticmethod
    def validate_rows(data, identities):
        if not isinstance(data, list) or not data:
            raise CollectorError("Ranking vazio ou inválido.")
        ids = set()
        try:
            for row in data:
                account = row["account"]
                identity, name = account["id"], account["full_name"]
                value = Decimal(str(row["score"]))
                if (
                    type(identity) is not int
                    or identity in ids
                    or not isinstance(name, str)
                    or not name.strip()
                    or not value.is_finite()
                    or value < 0
                    or (identity in identities and identities[identity] != name)
                ):
                    raise ValueError
                identities[identity] = name
                ids.add(identity)
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise CollectorError(
                "Participante duplicado, identidade ou valor inválido."
            ) from None
        return ids

    def original(self, run):
        folder = self.folder(run)
        manifest = read(folder / "manifest.json")
        if manifest.get("provisional"):
            first, month_end = bounds(manifest["month"], closed=False)
            last = date.fromisoformat(manifest["annual_end_date"])
            today = local_today()
            if not first <= last < min(month_end, today):
                raise CollectorError("Corte incompatível com uma prévia parcial.")
        else:
            first, last = bounds(manifest["month"])
        if (
            manifest["status"] != "complete"
            or manifest["completed"] != 7
            or manifest["challenge_id"] != DEFAULT_CHALLENGE_ID
            or manifest["annual_end_date"] != last.isoformat()
        ):
            raise CollectorError("A coleta está incompleta ou tem datas incompatíveis.")
        tables, seen, identities, expected = [], set(), {}, None
        for item in manifest["responses"]:
            key = item["period"], item["metric"]
            if key not in PLAN or key in seen:
                raise CollectorError("Métrica inválida ou repetida.")
            seen.add(key)
            period, metric = key
            # Filenames come from the fixed plan, never from a submitted path.
            capture = read(folder / f"{period}-{metric}.json")
            params = dict(capture["params"])
            start = first if period == "month" else first.replace(month=1)
            if capture[
                "path"
            ] != f"/challenges/{DEFAULT_CHALLENGE_ID}/rankings" or params != dict(
                disable_format="true",
                score_by=metric,
                start_date=start.isoformat(),
                end_date=last.isoformat(),
            ):
                raise CollectorError("Datas ou parâmetros incompatíveis.")
            if capture["response"].get("status") != "success":
                raise CollectorError("Resposta sem sucesso confirmado.")
            data = capture["response"]["data"]
            ids = self.validate_rows(data, identities)
            if expected is not None and ids != expected:
                raise CollectorError("Participantes divergem entre rankings.")
            expected = ids
            rows = tuple(
                DraftRow(
                    row["account"]["full_name"],
                    format(Decimal(str(row["score"])), "f")
                    + (" min" if metric == "duration" else ""),
                    row.get("rank"),
                )
                for row in data
            )
            tables.append(DraftTable(METRICS[metric], Period(period), rows))
        if len(seen) != 7:
            raise CollectorError("São necessários sete rankings.")
        return review(tables, self.repo.participants(), month=manifest["month"])

    def load_draft(self, run):
        with self.lock:
            original = self.original(run)
            path = self.folder(run) / "corrections.json"
            if not path.exists():
                save_private(path, {"revision": 1, "draft": draft_to_dict(original)})
            doc = read(path)
            stored = draft_from_dict(doc["draft"])
            draft = review(stored.tables, self.repo.participants(), month=original.month)
            return {
                **draft_to_dict(draft),
                "revision": doc["revision"],
                "run": run,
                "provisional": self.get(run)["provisional"],
                "annual_end_date": self.get(run)["annual_end_date"],
                "differences": self.tally.differences(original.month, to_tables(draft)),
            }

    def save_draft(self, run, tables, month, revision):
        with self.lock:
            current = self.load_draft(run)
            if month != current["month"] or revision != current["revision"]:
                raise CollectorError("Rascunho desatualizado. Reabra a conferência.")
            draft = review(tables, self.repo.participants(), month=month)
            save_private(
                self.folder(run) / "corrections.json",
                {"revision": revision + 1, "draft": draft_to_dict(draft)},
            )
            return self.load_draft(run)

    def fingerprint(self, run):
        # A preview also depends on the roster, historical months and published
        # state. Another tab changing any of those invalidates its confirmation.
        digest = hashlib.sha256()
        paths = [self.folder(run) / "corrections.json"]
        paths += sorted(self.repo.root.glob("*.json"))
        paths += sorted((self.repo.root / "months").glob("*.json"))
        paths += sorted((self.repo.root / "history").glob("*.json"))
        paths += sorted((self.repo.root / "previews").glob("*.json"))
        for path in paths:
            digest.update(str(path).encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def preview(self, run, revision):
        with self.lock:
            doc = self.load_draft(run)
            if revision != doc["revision"]:
                raise CollectorError("A prévia usa uma revisão desatualizada.")
            stored = draft_from_dict(doc)
            draft = review(stored.tables, self.repo.participants(), month=stored.month)
            blocking = [i for i in draft.issues if i.type != "position_mismatch"]
            if blocking:
                raise CollectorError(
                    "Resolva nomes, valores e tabelas destacados antes de continuar."
                )
            expected_keys = {(METRICS[m], Period(p)) for p, m in PLAN}
            keys = [(t.modality, t.period) for t in draft.tables]
            if len(keys) != 7 or set(keys) != expected_keys:
                raise CollectorError("Mantenha os sete rankings obrigatórios.")
            names = None
            for table in draft.tables:
                current = {r.resolved_name for r in table.rows}
                if not current or None in current or len(current) != len(table.rows):
                    raise CollectorError("Resolva todos os participantes.")
                if names is not None and current != names:
                    raise CollectorError(
                        "Participantes divergem entre rankings revisados."
                    )
                names = current
                if any(
                    r.value is None
                    or not math.isfinite(r.value)
                    or r.value < 0
                    or not valid_raw(table.modality, r.raw_value)
                    for r in table.rows
                ):
                    raise CollectorError("Há valores inválidos no rascunho.")
            tables = to_tables(draft)
            missing = self.tally.missing_months(doc["month"])
            if missing:
                raise CollectorError("Meses anteriores ausentes: " + ", ".join(missing))
            result = self.tally.preview(doc["month"], tables)
            documents = tally_result_to_dict(result.month, result.season)
            if doc["provisional"]:
                for document in documents.values():
                    document.update(provisional=True, data_through=doc["annual_end_date"])
            return {
                **documents,
                "provisional": doc["provisional"],
                "revision": revision,
                "preview_token": self.fingerprint(run),
                "issues": doc["issues"],
                "committed": False,
                "replacement": doc["month"] in self.repo.published_months(),
                "differences": self.tally.differences(doc["month"], tables),
                "annual_end_date": doc["annual_end_date"],
            }

    def commit(self, run, revision, token, replace):
        with self.lock:
            result = self.preview(run, revision)
            if token != result["preview_token"]:
                raise CollectorError("A prévia está desatualizada. Gere outra prévia.")
            if result["replacement"] and not replace:
                raise CollectorError("Confirme explicitamente a substituição deste mês.")
            doc = self.load_draft(run)
            provenance = dict(
                source="gymrats_api",
                challenge_id=DEFAULT_CHALLENGE_ID,
                monthly_start=doc["month"] + "-01",
                monthly_end=doc["annual_end_date"],
                annual_start="2026-01-01",
                annual_end=doc["annual_end_date"],
                revision=revision,
            )
            committed = self.tally.commit(
                doc["month"],
                to_tables(
                    review(
                        draft_from_dict(doc).tables,
                        self.repo.participants(),
                        month=doc["month"],
                    )
                ),
                provenance=provenance,
                provisional=doc["provisional"],
            )
            return {
                **result,
                "committed": True,
                "publication": "pending_git",
                "month_path": str(committed.month_path),
                "published": [str(p) for p in committed.published],
            }
