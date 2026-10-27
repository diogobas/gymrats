"""Standalone GymRats API research tool. Python 3.11+, standard library only."""

from __future__ import annotations

import argparse
import calendar
import getpass
import io
import json
import os
import re
import sys
import tempfile
import uuid
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import sleep
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

BASE_URL = "https://www.gymrats.app/api"
LOCAL = Path(__file__).resolve().parent / ".local"
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
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
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


def load_session():
    try:
        session = json.loads((LOCAL / "session.json").read_text())
        if not isinstance(session, dict) or not all(
            isinstance(session[key], str)
            and session[key]
            and not any(ch.isspace() for ch in session[key])
            for key in ("token", "signature")
        ):
            raise ValueError
        return session
    except (OSError, ValueError, KeyError, TypeError):
        raise CollectorError(
            "Sessão ausente ou inválida. Execute login ou auth-token."
        ) from None


def parameters(items):
    result = []
    for item in items:
        key, separator, value = item.partition("=")
        if not separator or not key:
            raise CollectorError("Cada --param deve ter o formato chave=valor.")
        if re.sub(r"[^a-z]", "", key.lower()) in SECRET_KEYS:
            raise CollectorError(
                "Credenciais não devem ser enviadas como filtros de URL."
            )
        result.append((key, value))
    return result


def shape(value, depth=0):
    """Describe fields and counts, without printing names, emails or metric values."""
    if isinstance(value, dict):
        if depth >= 3:
            return {"type": "object", "keys": list(value)[:30]}
        return {key: shape(item, depth + 1) for key, item in list(value.items())[:30]}
    if isinstance(value, list):
        return {
            "type": "array",
            "count": len(value),
            "first_item": shape(value[0], depth + 1) if value else None,
        }
    return type(value).__name__


def fetch(args, path, params, *, api_version=None):
    session = load_session()
    response = request_json(
        path,
        session=session,
        version=args.app_version,
        timezone=args.timezone,
        platform=args.platform,
        params=params,
        api_version=api_version or getattr(args, "api_version", None),
    )
    if not isinstance(response, dict) or response.get("status") != "success":
        raise CollectorError("A API não confirmou sucesso; resposta não gravada.")
    captured = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output = LOCAL / "responses" / f"{captured}-{uuid.uuid4().hex[:8]}.json"
    save_private(
        output,
        {
            "captured_at": datetime.now(UTC).isoformat(),
            "base_url": BASE_URL,
            "path": path,
            "params": params,
            "app_version": args.app_version,
            "timezone": args.timezone,
            "api_version": api_version or getattr(args, "api_version", None),
            "response": redact(response, (session["token"],)),
        },
    )
    print(f"Resposta salva: {output}")
    print(json.dumps(shape(response), ensure_ascii=False, indent=2))
    return output


def ranking_accounts(response):
    data = response.get("data") if isinstance(response, dict) else None
    if (
        not isinstance(response, dict)
        or response.get("status") != "success"
        or not isinstance(data, list)
        or not data
    ):
        raise CollectorError("Ranking vazio ou em formato inesperado.")
    ids = set()
    try:
        for row in data:
            account_id = row["account"]["id"]
            if type(account_id) is not int or account_id in ids:
                raise CollectorError("Ranking com ID de conta inválido ou duplicado.")
            if not Decimal(str(row["score"])).is_finite():
                raise CollectorError("Ranking com valor numérico inválido.")
            ids.add(account_id)
    except (KeyError, TypeError, InvalidOperation):
        raise CollectorError("Ranking sem conta ou valor numérico válido.") from None
    return ids


def collect_month(args):
    try:
        start = date.fromisoformat(args.month + "-01")
        if start.strftime("%Y-%m") != args.month:
            raise ValueError
    except ValueError:
        raise CollectorError("Mês deve ter formato YYYY-MM.") from None
    end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
    plan = [
        ("month", metric)
        for metric in ("points", "days", "calories", "distance", "duration")
    ]
    if args.include_year:
        plan.extend(("year", metric) for metric in ("distance", "duration"))
    run = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    manifest_path = LOCAL / "collections" / run / "manifest.json"
    manifest = {
        "schema_version": 1,
        "challenge_id": args.challenge_id,
        "month": args.month,
        "annual_end_date": end.isoformat() if args.include_year else None,
        "status": "partial",
        "responses": [],
        "same_accounts_in_all_rankings": None,
    }
    save_private(manifest_path, manifest)
    print(f"Manifesto da coleta: {manifest_path}")
    expected_ids = None
    for index, (period, metric) in enumerate(plan):
        if index:
            sleep(0.5)
        options = SimpleNamespace(
            start_date=(
                start if period == "month" else start.replace(month=1)
            ).isoformat(),
            end_date=end.isoformat(),
            limit=None,
            score_by=metric,
        )
        params = ranking_params(options)
        output = fetch(args, f"/challenges/{args.challenge_id}/rankings", params)
        captured = json.loads(output.read_text())
        ids = ranking_accounts(captured["response"])
        if expected_ids is None:
            expected_ids = ids
        manifest["responses"].append(
            {
                "period": period,
                "metric": metric,
                "count": len(ids),
                "file": str(output.relative_to(LOCAL)),
            }
        )
        consistent = ids == expected_ids
        manifest["same_accounts_in_all_rankings"] = consistent
        save_private(manifest_path, manifest)
        if not consistent:
            raise CollectorError(
                "Participantes diferem entre métricas; coleta ficou parcial."
            )
    manifest["status"] = "complete"
    save_private(manifest_path, manifest)
    print(f"Coleta concluída: {len(plan)} rankings, {len(expected_ids)} contas em cada.")
    print("Consistência entre rankings não garante presença de ex-membros do grupo.")


def auth_data(result):
    data = result.get("data") if isinstance(result, dict) else None
    if not isinstance(data, dict):
        raise CollectorError("Resposta de autenticação inesperada; conteúdo não gravado.")
    return data


def finish_login(session, result):
    token = auth_data(result).get("token")
    if not isinstance(token, str) or not token or any(ch.isspace() for ch in token):
        raise CollectorError("Login sem data.token válido. Resposta não gravada.")
    session["token"] = token
    save_private(LOCAL / "session.json", session)
    print("Sessão salva localmente. Credenciais e resposta de login não foram gravadas.")


def login_email(args):
    email = (args.email or input("E-mail vinculado à conta GymRats: ")).strip()
    if "@" not in email or any(ch.isspace() for ch in email):
        raise CollectorError("Informe o e-mail exato da sua conta existente.")
    session = {"signature": str(uuid.uuid4())}
    options = {
        "session": session,
        "version": args.app_version,
        "timezone": args.timezone,
        "platform": args.platform,
    }
    result = request_json(
        "/accounts/email_confirmation",
        **options,
        credentials={"email": email, "locale": args.locale},
    )
    nonce = auth_data(result).get("nonce")
    if not isinstance(nonce, str) or not nonce:
        raise CollectorError("Resposta sem data.nonce. Não foi possível iniciar o login.")
    print("Código solicitado. Consulte o e-mail e digite o código neste terminal.")
    code = getpass.getpass("Código de verificação GymRats: ").strip()
    if not code or len(code) > 128 or any(ch.isspace() for ch in code):
        raise CollectorError("Código vazio ou inválido. Nenhuma sessão foi substituída.")
    result = request_json(
        "/accounts/sign_in",
        **options,
        credentials={
            "token": code,
            "nonce": nonce,
            "region_code": args.region_code,
            "language_locale": args.locale,
        },
    )
    finish_login(session, result)


def ranking_params(args):
    if bool(args.start_date) != bool(args.end_date):
        raise CollectorError("Informe --start-date e --end-date juntos.")
    params = [("disable_format", "true"), ("score_by", args.score_by)]
    if args.limit is not None:
        if args.limit <= 0:
            raise CollectorError("--limit deve ser positivo.")
        params.append(("limit", str(args.limit)))
    if args.start_date:
        try:
            start = date.fromisoformat(args.start_date)
            end = date.fromisoformat(args.end_date)
        except ValueError:
            raise CollectorError("Datas devem ter formato YYYY-MM-DD.") from None
        if start.isoformat() != args.start_date or end.isoformat() != args.end_date:
            raise CollectorError("Datas devem ter formato YYYY-MM-DD.")
        if start > end:
            raise CollectorError(
                "A data inicial deve vir antes ou no mesmo dia da final."
            )
        params.extend([("start_date", args.start_date), ("end_date", args.end_date)])
    return params


def scan_bytes(raw, source):
    # Hermes/Dex can concatenate a route and the next string. Candidates need
    # manual confirmation; the surrounding strings help locate their call sites.
    pattern = rb"(GET|POST|PUT|PATCH|DELETE|HEAD) (/[-a-zA-Z0-9_/:.{}]+)"
    return [
        {
            "method": match[1].decode(),
            "candidate_path": match[2].decode(),
            "source": source,
            "offset": match.start(),
            "context": raw[max(0, match.start() - 60) : match.end() + 100].decode(
                "utf-8", errors="replace"
            ),
        }
        for match in re.finditer(pattern, raw)
    ]


def discover(path: Path):
    results = []
    if zipfile.is_zipfile(path):
        if path.stat().st_size > 256 * 1024 * 1024:
            raise CollectorError("Arquivo compactado maior que 256 MiB.")
        with zipfile.ZipFile(path) as archive:
            if "com.hasz.gymrats.app.apk" in archive.namelist():
                main = archive.getinfo("com.hasz.gymrats.app.apk")
                if main.file_size > MAX_BYTES:
                    raise CollectorError(
                        "APK principal maior que 64 MiB; extraia o bundle."
                    )
                with zipfile.ZipFile(io.BytesIO(archive.read(main))) as apk:
                    results = scan_archive(apk)
            else:
                results = scan_archive(archive)
    else:
        if path.stat().st_size > MAX_BYTES:
            raise CollectorError("Arquivo maior que 64 MiB. Forneça o bundle extraído.")
        results = scan_bytes(path.read_bytes(), path.name)
    output = LOCAL / "routes.json"
    save_private(output, results)
    print(f"{len(results)} candidatos salvos em {output}.")
    print("Candidatos não são rotas validadas. Nenhuma requisição foi enviada.")


def scan_archive(archive):
    results = []
    total = 0
    for info in archive.infolist():
        if not (info.filename.endswith(".dex") or "bundle" in info.filename):
            continue
        total += info.file_size
        if info.file_size > MAX_BYTES or total > 256 * 1024 * 1024:
            raise CollectorError("Conteúdo grande demais; forneça o bundle extraído.")
        results.extend(scan_bytes(archive.read(info), info.filename))
    return results


def import_har(path: Path):
    """Import GymRats session headers from a local HAR, including Apple logins."""
    if path.stat().st_size > MAX_BYTES:
        raise CollectorError(
            "HAR maior que 64 MiB. Exporte somente as consultas relevantes."
        )
    try:
        document = json.loads(path.read_text())
        entries = document["log"]["entries"]
        if not isinstance(entries, list):
            raise ValueError
        sessions = {}
        for entry in entries:
            request = entry["request"]
            url = urlsplit(request["url"])
            if (
                url.scheme != "https"
                or url.netloc != "www.gymrats.app"
                or not url.path.startswith("/api/")
            ):
                continue
            headers = {item["name"].lower(): item["value"] for item in request["headers"]}
            token = headers.get("authorization", "")
            if not token:
                continue
            if any(ch.isspace() for ch in token):
                raise CollectorError("Formato de Authorization inesperado no HAR.")
            signature = headers.get("x-signature") or str(uuid.uuid4())
            sessions[token] = {"token": token, "signature": signature}
        if len(sessions) != 1:
            raise CollectorError(
                "O HAR deve conter consultas autenticadas de uma única sessão GymRats."
            )
        save_private(LOCAL / "session.json", next(iter(sessions.values())))
    except (ValueError, KeyError, TypeError, AttributeError):
        raise CollectorError("HAR inválido. Nenhuma credencial foi importada.") from None
    print("Sessão importada do HAR; validade ainda não testada.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--app-version",
        default=APP_VERSION,
        help="Versão do APK analisado: 2026.10.25.",
    )
    parser.add_argument("--timezone", default="America/Toronto")
    parser.add_argument("--platform", choices=("Android", "iOS"), default="Android")
    parser.add_argument("--api-version", choices=("1", "2"))
    sub = parser.add_subparsers(dest="command", required=True)
    login = sub.add_parser(
        "login", help="Autenticar com e-mail e senha, solicitados no terminal."
    )
    login.add_argument("--email")
    email_login = sub.add_parser(
        "login-email", help="Entrar com código enviado ao e-mail."
    )
    email_login.add_argument("--email")
    email_login.add_argument("--locale", default="en")
    email_login.add_argument("--region-code", default="CA")
    sub.add_parser(
        "auth-token", help="Salvar um token de sessão existente, solicitado sem eco."
    )
    har = sub.add_parser("auth-har", help="Importar a sessão GymRats de um HAR local.")
    har.add_argument("file", type=Path)
    sub.add_parser(
        "logout", help="Remover a sessão local (não revoga o token no servidor)."
    )
    get = sub.add_parser("get", help="Consultar uma rota GET já identificada.")
    get.add_argument("path")
    get.add_argument("--param", action="append", default=[])
    members = sub.add_parser(
        "members", help="Consultar a rota de membros identificada no APK."
    )
    members.add_argument(
        "challenge_id",
        type=int,
        nargs="?",
        default=DEFAULT_CHALLENGE_ID,
        help="Padrão: Gymrats 2026! (2504035).",
    )
    members.add_argument("--param", action="append", default=[])
    sub.add_parser("account", help="Consultar a identidade da sessão atual.")
    sub.add_parser("challenges", help="Consultar os grupos da conta atual.")
    rankings = sub.add_parser("rankings", help="Consultar o ranking do grupo por datas.")
    rankings.add_argument(
        "challenge_id",
        type=int,
        nargs="?",
        default=DEFAULT_CHALLENGE_ID,
        help="Padrão: Gymrats 2026! (2504035).",
    )
    rankings.add_argument("--start-date")
    rankings.add_argument("--end-date")
    rankings.add_argument("--limit", type=int)
    rankings.add_argument(
        "--score-by",
        required=True,
        choices=(
            "points",
            "days",
            "calories",
            "distance",
            "duration",
            "steps",
            "workouts",
        ),
    )
    collect = sub.add_parser(
        "collect-month", help="Coletar o mês e os desempates anuais."
    )
    collect.add_argument(
        "challenge_id",
        type=int,
        nargs="?",
        default=DEFAULT_CHALLENGE_ID,
        help="Padrão: Gymrats 2026! (2504035).",
    )
    collect.add_argument("month", help="YYYY-MM")
    annual = collect.add_mutually_exclusive_group()
    annual.add_argument(
        "--include-year",
        action="store_true",
        default=True,
        help="Incluir desempates anuais até o último dia do mês (padrão).",
    )
    annual.add_argument(
        "--month-only",
        action="store_false",
        dest="include_year",
        help="Coletar só o mês para pesquisa; insuficiente para a prévia anual.",
    )
    scan = sub.add_parser(
        "discover", help="Buscar candidatos a rotas em APK/bundle local."
    )
    scan.add_argument("file", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "login":
            email = args.email or input("E-mail GymRats: ").strip()
            password = getpass.getpass("Senha GymRats: ")
            if not email or not password:
                raise CollectorError("E-mail e senha são obrigatórios.")
            session = {"signature": str(uuid.uuid4())}
            result = request_json(
                "/tokens",
                session=session,
                version=args.app_version,
                timezone=args.timezone,
                platform=args.platform,
                credentials={"email": email, "password": password},
            )
            finish_login(session, result)
        elif args.command == "login-email":
            login_email(args)
        elif args.command == "auth-token":
            token = getpass.getpass("Token de sessão GymRats: ").strip()
            if not token or any(ch.isspace() for ch in token):
                raise CollectorError("Token vazio ou inválido. Informe somente o token.")
            save_private(
                LOCAL / "session.json", {"token": token, "signature": str(uuid.uuid4())}
            )
            print("Token salvo; validade ainda não testada.")
        elif args.command == "logout":
            (LOCAL / "session.json").unlink(missing_ok=True)
            print("Sessão local removida. Respostas mantidas em .local/responses/.")
        elif args.command == "auth-har":
            import_har(args.file)
        elif args.command == "discover":
            discover(args.file)
        elif args.command in {"account", "challenges"}:
            fetch(args, "/" + args.command, [])
        elif args.command == "collect-month":
            collect_month(args)
        elif args.command == "rankings":
            params = ranking_params(args)
            fetch(args, f"/challenges/{args.challenge_id}/rankings", params)
            print("Confira a quantidade de membros; a completude ainda não foi validada.")
        else:
            path = (
                args.path
                if args.command == "get"
                else f"/challenges/{args.challenge_id}/members"
            )
            endpoint(path)
            fetch(
                args,
                path,
                parameters(args.param),
                api_version="2" if args.command == "members" else None,
            )
    except (CollectorError, OSError, zipfile.BadZipFile) as exc:
        # OSError text can include paths; don't echo user-supplied or server data.
        message = (
            str(exc)
            if isinstance(exc, CollectorError)
            else "Falha ao ler ou gravar arquivo local."
        )
        print(f"Erro: {message}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nOperação cancelada.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
