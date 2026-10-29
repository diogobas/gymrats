"""Configure cron-job.org without putting credentials in shell history or Git."""

import argparse
import getpass
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CREDENTIALS = ROOT / ".local/external-scheduler/credentials.json"
CRON_API = "https://api.cron-job.org"
WORKFLOW = (
    "https://api.github.com/repos/diogobas/gymrats/actions/workflows/refresh-data.yml"
)
TITLE = "GymRats - atualizacao diaria"
SCHEDULE = {
    "timezone": "America/Sao_Paulo",
    "expiresAt": 0,
    "hours": [0],
    "minutes": [7],
    "mdays": [-1],
    "months": [-1],
    "wdays": [-1],
}


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(method, url, token, payload=None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json"
        if url.startswith(WORKFLOW)
        else "application/json",
        "User-Agent": "gymrats-scheduler-setup",
    }
    if url.startswith(WORKFLOW):
        headers["X-GitHub-Api-Version"] = "2026-03-10"
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with build_opener(NoRedirects()).open(req, timeout=30) as response:
            body = response.read()
            return json.loads(body) if body else {}
    except HTTPError as error:
        # Do not print response bodies: an upstream error might echo credentials.
        raise RuntimeError(f"{method} {url}: HTTP {error.code}") from None
    except URLError:
        raise RuntimeError(f"{method} {url}: falha de conexao") from None


def save_credentials():
    cron_key = getpass.getpass("API key do cron-job.org (Settings): ").strip()
    github_token = getpass.getpass(
        "Token fine-grained do GitHub (somente GymRats): "
    ).strip()
    if not cron_key or not github_token:
        raise RuntimeError("As duas credenciais sao obrigatorias.")
    CREDENTIALS.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(CREDENTIALS, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as target:
        os.fchmod(target.fileno(), 0o600)
        json.dump({"cron_api_key": cron_key, "github_token": github_token}, target)
    print(
        "Credenciais salvas em .local/external-scheduler/credentials.json (fora do Git)."
    )


def find_job(cron_key):
    listing = request("GET", f"{CRON_API}/jobs", cron_key)
    if listing.get("someFailed"):
        raise RuntimeError(
            "Lista de jobs incompleta. Tente novamente antes de criar outro job."
        )
    matches = [
        job
        for job in listing["jobs"]
        if job["title"] == TITLE or job["url"] == f"{WORKFLOW}/dispatches"
    ]
    if len(matches) > 1:
        raise RuntimeError("Ha mais de um job GymRats. Confira as duplicatas no console.")
    if matches and matches[0]["url"] != f"{WORKFLOW}/dispatches":
        raise RuntimeError("O titulo ja pertence a outro destino. Confira o console.")
    return matches[0] if matches else None


def configure(credentials):
    cron_key = credentials["cron_api_key"]
    github_token = credentials["github_token"]
    workflow = request("GET", WORKFLOW, github_token)
    if workflow["state"] != "active":
        raise RuntimeError("O workflow do GitHub nao esta ativo.")
    existing = find_job(cron_key)
    job = {
        "title": TITLE,
        "url": f"{WORKFLOW}/dispatches",
        "enabled": True,
        "saveResponses": True,
        "requestMethod": 1,  # POST in the cron-job.org API.
        "schedule": SCHEDULE,
        "extendedData": {
            "headers": {
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "X-GitHub-Api-Version": "2026-03-10",
                "User-Agent": "gymrats-external-scheduler",
            },
            "body": json.dumps({"ref": "master"}),
        },
    }
    if existing:
        job_id = existing["jobId"]
        request("PATCH", f"{CRON_API}/jobs/{job_id}", cron_key, {"job": job})
    else:
        result = request("PUT", f"{CRON_API}/jobs", cron_key, {"job": job})
        job_id = result["jobId"]
    saved = request("GET", f"{CRON_API}/jobs/{job_id}", cron_key)["jobDetails"]
    if any(
        saved.get(key) != job[key]
        for key in ("enabled", "url", "requestMethod", "schedule", "extendedData")
    ):
        raise RuntimeError(
            "O servico nao confirmou a configuracao completa. Confira o console."
        )
    print(f"Job {job_id} configurado: diariamente as 00:07 de Sao Paulo.")
    print(
        "Execute um teste no console do cron-job.org antes de remover o cron do GitHub."
    )
    status(credentials)


def status(credentials):
    cron_key = credentials["cron_api_key"]
    job = find_job(cron_key)
    if not job:
        raise RuntimeError("Agendamento externo ainda nao criado.")
    # Never print extendedData, which contains the GitHub token.
    print(
        json.dumps(
            {
                key: job.get(key)
                for key in (
                    "jobId",
                    "enabled",
                    "schedule",
                    "lastStatus",
                    "lastExecution",
                    "nextExecution",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if job.get("nextExecution"):
        upcoming = datetime.fromtimestamp(
            job["nextExecution"], ZoneInfo("America/Sao_Paulo")
        )
        print(f"Proxima execucao em Sao Paulo: {upcoming.isoformat()}")
    history = request("GET", f"{CRON_API}/jobs/{job['jobId']}/history", cron_key)
    for entry in history["history"][:5]:
        print(
            json.dumps(
                {
                    key: entry.get(key)
                    for key in ("date", "datePlanned", "jitter", "status", "httpStatus")
                }
            )
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("credentials", "configure", "status"))
    args = parser.parse_args()
    try:
        if args.action == "credentials":
            save_credentials()
            return
        if not CREDENTIALS.exists():
            raise RuntimeError(
                "Execute primeiro: python3 scripts/setup_external_schedule.py credentials"
            )
        credentials = json.loads(CREDENTIALS.read_text())
        {"configure": configure, "status": status}[args.action](credentials)
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        # JSON parsing and key errors should not reveal credential file contents.
        message = (
            str(error)
            if isinstance(error, RuntimeError)
            else "Falha ao ler a configuracao ou resposta da API."
        )
        parser.exit(1, f"{message}\n")


if __name__ == "__main__":
    main()
