from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts import brand, intake

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_CSV = REPO_ROOT / "examples" / "demo-meta-export.csv"


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    shutil.copytree(REPO_ROOT / "clients" / "_template", tmp_path / "clients" / "_template")
    return tmp_path


@pytest.mark.parametrize(
    ("name", "slug"),
    [("Acme Plumbing Ltd", "acme-plumbing"), ("Café & Co. Limited", "caf-co"), ("  ", "client"), ("BRIGHT LLP", "bright")],
)
def test_slugify(name: str, slug: str):
    assert intake.slugify(name) == slug


def test_intake_creates_client_runs_audit_and_drafts_email(workspace: Path, capsys: pytest.CaptureFixture[str]):
    code = intake.main(
        [
            "Northfield Coffee Ltd",
            str(DEMO_CSV),
            "--max-cpa",
            "18",
            "--email",
            "jo@example.com",
            "--contact",
            "Jo Smith",
            "--monthly-spend",
            "3600",
            "--founding",
        ]
    )
    assert code == 0
    root = workspace / "clients" / "northfield-coffee"
    cfg = json.loads((root / "client.json").read_text())
    assert cfg["engagement"] == {"relationship": "client", "offer": "ad-waste-audit", "status": "active", "founding": True}
    assert cfg["contact"] == {"name": "Jo Smith", "email": "jo@example.com"}
    budgets = json.loads((root / "budgets.json").read_text())
    assert budgets["target_cpa"] == 18
    assert budgets["min_spend_to_judge"] == 36
    assert budgets["daily_cap"] == 120
    assert (root / "data" / DEMO_CSV.name).exists()
    email = next((root / "reports").glob("email-*.txt")).read_text()
    service = brand.load().service_name
    assert email.startswith(f"Subject: Your {service} report:")
    assert "Hi Jo," in email
    assert "refund" not in email.lower()
    assert len(list((root / "reports").glob("ad-waste-audit-*.html"))) == 1
    out = capsys.readouterr().out
    assert "founding client" in out
    assert "refund" not in out


def test_intake_drafts_refund_email_below_guarantee(workspace: Path, capsys: pytest.CaptureFixture[str]):
    csv = workspace / "small.csv"
    csv.write_text("ad_name,spend,impressions,clicks,conversions\nA,50,3000,30,0\nB,400,9000,200,30\n")
    assert intake.main(["Tiny Shop", str(csv), "--max-cpa", "20", "--days", "30"]) == 0
    email = next((workspace / "clients" / "tiny-shop" / "reports").glob("email-*.txt")).read_text()
    assert "refunded your payment in full" in email
    assert "ACTION:  below the guarantee threshold" in capsys.readouterr().out


def test_intake_reuses_existing_client_and_updates_target(workspace: Path):
    intake.prepare_client("Acme", 20)
    client = intake.prepare_client("Acme", 30, email="new@acme.test")
    assert client.contact_email == "new@acme.test"
    assert json.loads((client.budgets_path).read_text())["target_cpa"] == 30


def test_intake_rejects_bad_input(workspace: Path, capsys: pytest.CaptureFixture[str]):
    assert intake.main(["Acme", "missing.csv", "--max-cpa", "20"]) == 1
    bad = workspace / "bad.csv"
    bad.write_text("x,y\n1,2\n")
    assert intake.main(["Acme", str(bad), "--max-cpa", "20"]) == 1
    assert intake.main(["Acme", str(DEMO_CSV), "--max-cpa", "0"]) == 1
    assert capsys.readouterr().err.count("error:") == 3
