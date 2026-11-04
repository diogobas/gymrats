"""Explicit API account bindings, independent of editable profile names."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal

from ..core.models import Modality, Period
from ..core.ranking import competition_rank
from ..core.roster import Roster
from .client import DEFAULT_CHALLENGE_ID, CollectorError


def account_key(identity: int) -> str:
    # Keep raw API account IDs out of versioned configuration and public builds.
    return hashlib.sha256(
        f"gymrats:{DEFAULT_CHALLENGE_ID}:{identity}".encode()
    ).hexdigest()


class AccountBindings:
    def __init__(self, repo):
        self.repo = repo
        self.roster = Roster(repo.participants())
        path = repo.root / "collection-accounts.json"
        doc = json.loads(path.read_text()) if path.exists() else {}
        self.names = doc.get("participants", {})
        self.ignored = doc.get("ignored", [])
        self.retired = doc.get("retired", {})
        if (
            not isinstance(self.names, dict)
            or not isinstance(self.ignored, list)
            or not isinstance(self.retired, dict)
            or any(
                not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key)
                for key in [*self.names, *self.ignored, *self.retired]
            )
            or set(self.names) & set(self.ignored)
            or any(
                not isinstance(name, str) or self.roster.get(name) is None
                for name in self.names.values()
            )
            or len(set(self.names.values())) != len(self.names)
        ):
            raise CollectorError(
                "Configuração de contas inválida: collection-accounts.json."
            )
        for key, rule in self.retired.items():
            if (
                not isinstance(rule, dict)
                or rule.get("replacement") not in self.names
                or key in self.names
                or key in self.ignored
                or not re.fullmatch(r"2026-(?:0[1-9]|1[01])", rule.get("last_month", ""))
                or not isinstance(rule.get("opening_values"), dict)
                or any(
                    type(rule["opening_values"].get(metric)) not in (int, float)
                    or not Decimal(str(rule["opening_values"][metric])).is_finite()
                    or rule["opening_values"][metric] < 0
                    for metric in ("distance", "duration")
                )
            ):
                raise CollectorError("Configuração de substituição de contas inválida.")

    def select(self, data, *, month, period, metric):
        selected = []
        by_key = {account_key(row["account"]["id"]): row for row in data}
        replacements = {}
        historical = {}
        for key, rule in self.retired.items():
            replacement = rule["replacement"]
            name = self.names.get(replacement)
            last_month = rule["last_month"]
            if name is None or key in self.names or key in self.ignored:
                raise CollectorError("Configuração de substituição de contas inválida.")
            if month <= last_month:
                # Before the switch both accounts belong to the same competitor.
                if key in by_key:
                    historical[replacement] = key
                    previous = by_key[key]
                    current = by_key.get(replacement)
                    score = Decimal(str(previous["score"]))
                    if current:
                        score += Decimal(str(current["score"]))
                    replacements[key] = (name, score)
            elif period == "year":
                # Preserve the old account's history through the reviewed cutoff;
                # never include its activities from the replacement month onward.
                if replacement not in by_key:
                    raise CollectorError("A conta substituta não está no ranking da API.")
                baseline = self.repo.public_tables(last_month)
                carried = baseline.value_for(name, Modality(metric), Period.YEAR)
                if carried is None:
                    raise CollectorError("Histórico da conta anterior ausente.")
                score = Decimal(str(by_key[replacement]["score"]))
                score += Decimal(str(carried))
                score -= Decimal(str(rule["opening_values"][metric]))
                if score < Decimal(str(carried)):
                    raise CollectorError("Acumulado da conta substituta recuou.")
                replacements[replacement] = (name, score)
        for row in data:
            key = account_key(row["account"]["id"])
            if (
                key in self.ignored
                or key in historical
                or (key in self.retired and key not in replacements)
            ):
                continue
            if key in replacements:
                name, score = replacements[key]
                row = {**row, "score": str(score)}
            else:
                name = self.names.get(key)
            if name:
                resolved = self.roster.resolve(row["account"]["full_name"]).canonical
                if resolved is not None and resolved != name:
                    raise CollectorError(
                        "A conta da API conflita com o participante cadastrado."
                    )
                row = {**row, "account": {**row["account"], "full_name": name}}
            selected.append(row)
        if len(selected) != len(data) or replacements:
            # Removing a duplicate changes ranks. Check the source first, then
            # renumber the retained rows without changing any scores.
            def ranks(rows):
                return competition_rank(
                    (str(row["account"]["id"]), float(row["score"])) for row in rows
                )

            source_ranks = ranks(data)
            if any(
                row.get("rank") is not None
                and row["rank"] != source_ranks[str(row["account"]["id"])]
                for row in data
            ):
                raise CollectorError(
                    "Posições inconsistentes no ranking original da API."
                )
            selected_ranks = ranks(selected)
            selected = [
                {**row, "rank": selected_ranks[str(row["account"]["id"])]}
                for row in selected
            ]
        return selected
