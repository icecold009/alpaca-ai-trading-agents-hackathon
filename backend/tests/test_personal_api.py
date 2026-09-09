from pathlib import Path

from fastapi.testclient import TestClient

from riskcourt.app import create_app
from riskcourt.settings import RuntimeMode, Settings


def client_for(tmp_path: Path) -> TestClient:
    settings = Settings(
        riskcourt_mode=RuntimeMode.RECORDED,
        riskcourt_state_dir=tmp_path / ".riskcourt",
    )
    return TestClient(create_app(settings))


def test_personal_recorded_workspace_scan_and_approval(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        account = client.get("/api/account/summary")
        assert account.status_code == 200
        assert account.json()["mode"] == "recorded"

        scan = client.post("/api/scans", json={"symbols": ["SPY", "QQQ"]})
        assert scan.status_code == 200
        payload = scan.json()
        assert payload["status"] == "completed"
        assert payload["decisions"][0]["symbol"] == "SPY"
        assert payload["failures"] == [{"symbol": "QQQ", "reason": "recorded_case_unavailable"}]

        decision_id = payload["decisions"][0]["decision_id"]
        approval = client.post(f"/api/decisions/{decision_id}/approve")
        assert approval.status_code == 200
        approval_id = approval.json()["approval"]["approval_id"]

        blocked = client.post(
            f"/api/approvals/{approval_id}/submit",
            json={"confirm": True, "idempotency_key": "riskcourt_test_order"},
        )
        assert blocked.status_code == 409
        assert "recorded mode" in blocked.json()["detail"]


def test_personal_workspace_veto_and_journal(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        scan = client.post("/api/scans", json={"symbols": ["SPY"]})
        decision_id = scan.json()["decisions"][0]["decision_id"]
        veto = client.post(f"/api/decisions/{decision_id}/veto")
        assert veto.status_code == 200
        assert veto.json()["status"] == "vetoed"

        journal = client.post(
            "/api/journal",
            json={"body": "Keep the edge threshold conservative.", "decision_id": decision_id},
        )
        assert journal.status_code == 200
        assert client.get("/api/journal").json()["entries"][0]["body"].startswith("Keep")
        audit = client.get("/api/audit")
        assert audit.status_code == 200
        assert any(item["event_type"] == "journal.created" for item in audit.json()["events"])


def test_personal_workspace_read_models_and_guardrails(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        assert client.get("/api/watchlist").json()["symbols"]
        updated = client.post("/api/watchlist", json={"symbols": ["QQQ"]})
        assert updated.status_code == 200
        scan = client.post("/api/scans", json={"symbols": ["SPY"]}).json()
        scan_id = scan["scan_id"]
        decision_id = scan["decisions"][0]["decision_id"]

        assert client.get(f"/api/scans/{scan_id}").status_code == 200
        assert client.get("/api/decisions").json()["decisions"]
        assert client.get(f"/api/decisions/{decision_id}").status_code == 200
        assert client.get("/api/orders").json()["orders"] == []
        assert client.get("/api/positions").json()["positions"] == []

        kill = client.post("/api/kill-switch", json={"enabled": True, "reason": "pause"})
        assert kill.status_code == 200
        assert kill.json()["kill_switch"]["enabled"] is True
        assert (
            client.post("/api/kill-switch", json={"enabled": False, "reason": "resume"}).status_code
            == 200
        )

        assert client.post("/api/positions/missing/exit-preview").status_code == 404
        assert (
            client.post(
                "/api/positions/missing/exit-submit",
                json={"confirm": True, "idempotency_key": "riskcourt_exit_test"},
            ).status_code
            == 404
        )
