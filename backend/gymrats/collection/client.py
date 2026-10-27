"""Private GymRats transport shared by the CLI and local admin."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE_URL = "https://www.gymrats.app/api"
MAX_BYTES = 64 * 1024 * 1024
APP_VERSION = "2026.10.25"
DEFAULT_CHALLENGE_ID = 2504035
AUTH_PATHS = {"/tokens", "/accounts/email_confirmation", "/accounts/sign_in"}
SECRET_KEYS = {
    "token",
    "accesstoken",
    "refreshtoken",
    "idtoken",
    "password",
    "authorization",
    "cookie",
    "setcookie",
    "secret",
    "clientsecret",
    "apikey",
    "nonce",
    "verificationcode",
}


class CollectorError(Exception):
    """An error safe to display without leaking the remote response or credentials."""


def redact(value, secrets=()):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if re.sub(r"[^a-z]", "", key.lower()) in SECRET_KEYS
            else redact(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
    return value


def save_private(path: Path, document):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward account credentials or the session token to another URL.
        return None


def endpoint(path: str) -> str:
    parsed = urlsplit(path)
    if (
        not path.startswith("/")
        or path.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or any(part in {".", ".."} for part in path.split("/"))
        or re.search(r"[\s\\%]", path)
    ):
        raise CollectorError(
            "Use uma rota relativa à API, sem query; filtros vão em --param."
        )
    if ":" in path or "{" in path or "}" in path:
        raise CollectorError(
            "Substitua os parâmetros da rota, como :challengeId, pelo ID real."
        )
    return BASE_URL + path


def request_json(
    path,
    *,
    session,
    version,
    timezone,
    platform="Android",
    params=None,
    credentials=None,
    api_version=None,
    opener_factory=None,
):
    url = endpoint(path)
    if params:
        url += "?" + urlencode(params)
    headers = {
        "Accept": "application/json",
        "x-signature": session["signature"],
        "rat-app-version": version,
        "rat-app-platform": platform,
        "rat-timezone": timezone,
    }
    body = None
    if api_version is not None:
        headers["api-version"] = api_version
    if credentials is not None:
        if path not in AUTH_PATHS:
            raise CollectorError("POST permitido somente nas rotas de autenticação.")
        body = json.dumps(credentials).encode()
        headers["Content-Type"] = "application/json"
    else:
        headers["Authorization"] = session["token"]
    request = Request(url, data=body, headers=headers)
    try:
        with (opener_factory or build_opener)(NoRedirect()).open(
            request, timeout=30
        ) as response:
            raw = response.read(MAX_BYTES + 1)
    except HTTPError as exc:
        hints = {
            401: "Sessão recusada ou expirada. Autentique novamente.",
            403: "Acesso recusado para esta conta; confira a permissão e a rota.",
            404: "Rota não encontrada. Confira a versão atual do aplicativo.",
            429: "Limite de requisições atingido. Aguarde antes de tentar novamente.",
        }
        raise CollectorError(
            f"HTTP {exc.code}. "
            + hints.get(exc.code, "Consulta falhou; resposta não exibida.")
        ) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise CollectorError("Falha de conexão ou cabeçalhos inválidos.") from None
    if len(raw) > MAX_BYTES:
        raise CollectorError("Resposta maior que o limite de 64 MiB.")
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError):
        raise CollectorError(
            "O servidor não retornou JSON válido; resposta não exibida."
        ) from None
