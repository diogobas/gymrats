"""Offline checks for credential handling and captured data in the isolated tool."""

import importlib.util
import io
import json
import stat
import zipfile
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1] / "experiments/gymrats_collector/collector.py"
)
spec = importlib.util.spec_from_file_location("experimental_collector", SCRIPT)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.setattr(collector, "LOCAL", tmp_path / ".local")
    return collector.LOCAL


@pytest.mark.parametrize(
    "path",
    [
        "https://other.test/",
        "//other.test/",
        "/../tokens",
        "/%2e%2e/tokens",
        "/members?token=secret",
        "/members#fragment",
        "/api\\other",
        "/challenges/:challengeId/members",
        "/members\n",
    ],
)
def test_rejects_routes_that_could_leak_credentials_or_have_placeholders(path):
    with pytest.raises(collector.CollectorError):
        collector.endpoint(path)


def test_transport_sends_get_with_token_and_encoded_filters(monkeypatch):
    seen = []

    class Opener:
        def open(self, request, timeout):
            seen.append(request)
            assert timeout == 30
            return io.BytesIO(b'{"data": []}')

    def opener(handler):
        assert isinstance(handler, collector.NoRedirect)
        return Opener()

    monkeypatch.setattr(collector, "build_opener", opener)
    assert collector.request_json(
        "/challenges/123/members",
        session={"token": "sensitive", "signature": "uuid"},
        version="2026.02.13",
        timezone="America/Toronto",
        params=[("name", "a&b"), ("page", "2")],
    ) == {"data": []}
    assert seen[0].get_method() == "GET"
    assert seen[0].get_header("Authorization") == "sensitive"
    assert seen[0].full_url.endswith("?name=a%26b&page=2")


@pytest.mark.parametrize("status", [302, 401, 403, 404, 429, 500])
def test_remote_errors_do_not_echo_bodies_headers_or_tokens(status, monkeypatch):
    class Opener:
        def open(self, request, timeout):
            raise HTTPError(
                "secret-url", status, "secret-token", {}, io.BytesIO(b"secret")
            )

    monkeypatch.setattr(collector, "build_opener", lambda handler: Opener())
    with pytest.raises(collector.CollectorError, match=f"HTTP {status}") as error:
        collector.request_json(
            "/members",
            session={"token": "secret-token", "signature": "uuid"},
            version="version",
            timezone="timezone",
        )
    assert "secret" not in str(error.value)


def test_redirect_handler_never_forwards_a_request():
    assert (
        collector.NoRedirect().redirect_request(
            None, None, 302, "redirect", {}, "https://other.test"
        )
        is None
    )


def test_login_saves_only_session_with_private_permissions(local, monkeypatch, capsys):
    monkeypatch.setattr(collector.getpass, "getpass", lambda prompt: "my-password")

    def login(path, **kwargs):
        assert path == "/tokens"
        assert kwargs["credentials"] == {
            "email": "me@example.test",
            "password": "my-password",
        }
        return {"data": {"token": "my-token", "email": "me@example.test"}}

    monkeypatch.setattr(collector, "request_json", login)
    assert collector.main(["login", "--email", "me@example.test"]) == 0
    saved = local / "session.json"
    assert set(json.loads(saved.read_text())) == {"token", "signature"}
    assert stat.S_IMODE(saved.stat().st_mode) == 0o600
    assert "my-password" not in saved.read_text()
    assert "my-token" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "result", [{}, {"data": None}, {"data": {"token": "bad\ntoken"}}]
)
def test_invalid_login_does_not_replace_an_existing_session(local, monkeypatch, result):
    collector.save_private(local / "session.json", {"token": "old", "signature": "uuid"})
    monkeypatch.setattr(collector.getpass, "getpass", lambda prompt: "password")
    monkeypatch.setattr(collector, "request_json", lambda *a, **kw: result)
    assert collector.main(["login", "--email", "me@example.test"]) == 1
    assert collector.load_session()["token"] == "old"


def test_capture_retains_metrics_but_removes_secrets(local, monkeypatch, capsys):
    collector.save_private(
        local / "session.json", {"token": "my-token", "signature": "uuid"}
    )
    monkeypatch.setattr(
        collector,
        "request_json",
        lambda *a, **kw: {
            "status": "success",
            "data": [
                {"name": "Person", "distance": 12.5, "access_token": "another-token"}
            ],
            "debug": "copied my-token",
            "Password": "password",
        },
    )
    args = SimpleNamespace(app_version="version", timezone="timezone", platform="iOS")
    collector.fetch(args, "/challenges/123/members", [])
    response = json.loads(next((local / "responses").glob("*.json")).read_text())
    assert response["response"]["data"][0]["distance"] == 12.5
    text = json.dumps(response)
    assert "my-token" not in text
    assert "another-token" not in text
    assert "Person" not in capsys.readouterr().out


def test_discovery_reads_apk_without_extracting_or_querying_it(local, tmp_path):
    apk = tmp_path / "app.apk"
    with zipfile.ZipFile(apk, "w") as archive:
        archive.writestr(
            "assets/index.android.bundle", b"\x00GET /challenges/:challengeId/members\x00"
        )
        archive.writestr("../../escape", b"ignored")
    collector.discover(apk)
    routes = json.loads((local / "routes.json").read_text())
    assert routes[0]["candidate_path"] == "/challenges/:challengeId/members"
    assert not (tmp_path.parent / "escape").exists()


def test_har_import_uses_only_authenticated_gymrats_requests(local, tmp_path):
    har = tmp_path / "capture.har"
    har.write_text(
        json.dumps(
            {
                "log": {
                    "entries": [
                        {
                            "request": {
                                "url": "https://apple.com/api/login",
                                "headers": [
                                    {"name": "Authorization", "value": "apple-token"},
                                ],
                            }
                        },
                        {
                            "request": {
                                "url": "https://www.gymrats.app/api/challenges/123/members",
                                "headers": [
                                    {"name": "Authorization", "value": "gymrats-token"},
                                    {
                                        "name": "x-signature",
                                        "value": "original-signature",
                                    },
                                ],
                            }
                        },
                    ]
                }
            }
        )
    )
    collector.import_har(har)
    assert collector.load_session() == {
        "token": "gymrats-token",
        "signature": "original-signature",
    }


def test_logout_preserves_captured_responses(local):
    collector.save_private(
        local / "session.json", {"token": "token", "signature": "uuid"}
    )
    collector.save_private(local / "responses/retained.json", {"data": []})
    assert collector.main(["logout"]) == 0
    assert not (local / "session.json").exists()
    assert (local / "responses/retained.json").exists()


@pytest.mark.parametrize("body", [b"<html>private</html>", b"\xff"])
def test_non_json_response_is_not_displayed_or_written(local, monkeypatch, body):
    class Opener:
        def open(self, request, timeout):
            return io.BytesIO(body)

    monkeypatch.setattr(collector, "build_opener", lambda handler: Opener())
    with pytest.raises(collector.CollectorError, match="JSON válido"):
        collector.request_json(
            "/members",
            session={"token": "token", "signature": "uuid"},
            version="version",
            timezone="timezone",
        )
    assert not local.exists()


def test_post_is_restricted_to_login():
    with pytest.raises(collector.CollectorError, match="POST permitido somente"):
        collector.request_json(
            "/challenges",
            session={"signature": "uuid"},
            version="version",
            timezone="timezone",
            credentials={"name": "do not create"},
        )


def test_filters_preserve_repeated_keys_and_reject_credentials():
    assert collector.parameters(["ids=1", "ids=2"]) == [("ids", "1"), ("ids", "2")]
    with pytest.raises(collector.CollectorError, match="Credenciais"):
        collector.parameters(["access_token=secret"])


def test_discovery_handles_concatenated_hermes_strings():
    routes = collector.scan_bytes(b"SomeLabelGET /challenges/:id/members\x00", "bundle")
    assert routes[0]["candidate_path"] == "/challenges/:id/members"


def test_email_login_reuses_signature_and_keeps_code_and_nonce_off_disk(
    local, monkeypatch, capsys
):
    calls = []

    def request(path, **kwargs):
        calls.append((path, kwargs["credentials"], kwargs["session"]["signature"]))
        if path == "/accounts/email_confirmation":
            return {"status": "success", "data": {"nonce": "secret-nonce"}}
        return {"status": "success", "data": {"token": "session-token"}}

    monkeypatch.setattr(collector, "request_json", request)
    monkeypatch.setattr(collector.getpass, "getpass", lambda prompt: "123456")
    assert collector.main(["login-email", "--email", "existing@example.test"]) == 0
    assert calls[0][1] == {"email": "existing@example.test", "locale": "en"}
    assert calls[1][0] == "/accounts/sign_in"
    assert calls[1][1] == {
        "token": "123456",
        "nonce": "secret-nonce",
        "region_code": "CA",
        "language_locale": "en",
    }
    assert calls[0][2] == calls[1][2]
    saved = (local / "session.json").read_text()
    assert "secret-nonce" not in saved
    assert "123456" not in saved
    assert "existing@example.test" not in saved
    output = capsys.readouterr().out
    assert "123456" not in output
    assert "session-token" not in output


@pytest.mark.parametrize("result", [{"data": {}}, {"status": "error"}, {"data": None}])
def test_email_login_stops_before_asking_for_code_when_nonce_is_missing(
    local, monkeypatch, result
):
    collector.save_private(local / "session.json", {"token": "old", "signature": "uuid"})
    monkeypatch.setattr(collector, "request_json", lambda *a, **kw: result)

    def unexpected_prompt(prompt):
        pytest.fail("Must not prompt for a code without a nonce")

    monkeypatch.setattr(collector.getpass, "getpass", unexpected_prompt)
    assert collector.main(["login-email", "--email", "existing@example.test"]) == 1
    assert collector.load_session()["token"] == "old"


@pytest.mark.parametrize("score", ["points", "days", "calories", "distance", "duration"])
def test_rankings_command_uses_dates_and_metrics_from_the_native_app(score, monkeypatch):
    calls = []
    monkeypatch.setattr(collector, "fetch", lambda *a, **kw: calls.append(a))
    assert (
        collector.main(
            [
                "rankings",
                "123",
                "--score-by",
                score,
                "--start-date",
                "2026-06-01",
                "--end-date",
                "2026-06-30",
                "--limit",
                "100",
            ]
        )
        == 0
    )
    assert calls[0][1] == "/challenges/123/rankings"
    assert dict(calls[0][2]) == {
        "disable_format": "true",
        "score_by": score,
        "limit": "100",
        "start_date": "2026-06-01",
        "end_date": "2026-06-30",
    }


@pytest.mark.parametrize(
    "options",
    [
        ["--start-date", "2026-06-01"],
        ["--start-date", "2026-06-30", "--end-date", "2026-06-01"],
        ["--start-date", "2026-02-30", "--end-date", "2026-06-01"],
        ["--limit", "0"],
    ],
)
def test_invalid_rankings_options_do_not_make_requests(options, monkeypatch):
    def unexpected_request(*args, **kwargs):
        pytest.fail("Invalid arguments must not trigger a request")

    monkeypatch.setattr(collector, "fetch", unexpected_request)
    assert collector.main(["rankings", "123", "--score-by", "points", *options]) == 1


def test_xapk_discovery_reads_only_the_main_apk(local, tmp_path):
    apk = io.BytesIO()
    with zipfile.ZipFile(apk, "w") as archive:
        archive.writestr("assets/index.android.bundle", b"GET /challenges\x00")
    xapk = tmp_path / "app.xapk"
    with zipfile.ZipFile(xapk, "w") as archive:
        archive.writestr("com.hasz.gymrats.app.apk", apk.getvalue())
        archive.writestr("config.arm64.apk", b"not read")
    collector.discover(xapk)
    routes = json.loads((local / "routes.json").read_text())
    assert len(routes) == 1
    assert routes[0]["candidate_path"] == "/challenges"


def test_members_command_uses_api_v2(monkeypatch):
    calls = []
    monkeypatch.setattr(collector, "fetch", lambda *a, **kw: calls.append((a, kw)))
    assert collector.main(["members", "123", "--param", "next=cursor"]) == 0
    assert calls[0][0][1:] == ("/challenges/123/members", [("next", "cursor")])
    assert calls[0][1]["api_version"] == "2"


def test_collect_month_saves_seven_rankings_and_exact_calendar_bounds(local, monkeypatch):
    calls = []
    monkeypatch.setattr(collector, "sleep", lambda delay: None)

    def fetch(args, path, params):
        calls.append((path, dict(params)))
        output = local / "responses" / f"{len(calls)}.json"
        collector.save_private(
            output,
            {
                "response": {
                    "status": "success",
                    "data": [
                        {"account": {"id": 42}, "score": "12.3456789", "rank": 1},
                    ],
                }
            },
        )
        return output

    monkeypatch.setattr(collector, "fetch", fetch)
    assert collector.main(["collect-month", "123", "2024-02", "--include-year"]) == 0
    assert len(calls) == 7
    for _, params in calls[:5]:
        assert params["start_date"] == "2024-02-01"
        assert params["end_date"] == "2024-02-29"
        assert "limit" not in params
    for _, params in calls[5:]:
        assert params["start_date"] == "2024-01-01"
        assert params["end_date"] == "2024-02-29"
    manifest = json.loads(
        next((local / "collections").glob("*/manifest.json")).read_text()
    )
    assert manifest["status"] == "complete"
    assert manifest["same_accounts_in_all_rankings"] is True
    assert len(manifest["responses"]) == 7


def test_collect_month_preserves_partial_manifest_when_members_change(local, monkeypatch):
    calls = []
    monkeypatch.setattr(collector, "sleep", lambda delay: None)

    def fetch(args, path, params):
        calls.append(path)
        output = local / "responses" / f"{len(calls)}.json"
        collector.save_private(
            output,
            {
                "response": {
                    "status": "success",
                    "data": [
                        {"account": {"id": len(calls)}, "score": "10"},
                    ],
                }
            },
        )
        return output

    monkeypatch.setattr(collector, "fetch", fetch)
    assert collector.main(["collect-month", "123", "2026-06"]) == 1
    assert len(calls) == 2
    manifest = json.loads(
        next((local / "collections").glob("*/manifest.json")).read_text()
    )
    assert manifest["status"] == "partial"
    assert manifest["same_accounts_in_all_rankings"] is False
    assert len(manifest["responses"]) == 2


@pytest.mark.parametrize(
    "response",
    [
        {"status": "error", "data": []},
        {"status": "success", "data": []},
        {"status": "success", "data": [{"account": {"id": 1}, "score": "NaN"}]},
        {"status": "success", "data": [{"account": {"id": 1}, "score": "Infinity"}]},
        {
            "status": "success",
            "data": [
                {"account": {"id": 1}, "score": "1"},
                {"account": {"id": 1}, "score": "2"},
            ],
        },
    ],
)
def test_collection_rejects_invalid_or_duplicate_rankings(response):
    with pytest.raises(collector.CollectorError):
        collector.ranking_accounts(response)


def test_fetch_does_not_treat_api_error_in_http_200_as_success(local, monkeypatch):
    collector.save_private(
        local / "session.json", {"token": "token", "signature": "uuid"}
    )
    monkeypatch.setattr(collector, "request_json", lambda *a, **kw: {"status": "error"})
    args = SimpleNamespace(app_version="version", timezone="timezone", platform="Android")
    with pytest.raises(collector.CollectorError, match="não confirmou sucesso"):
        collector.fetch(args, "/challenges", [])
    assert not (local / "responses").exists()
