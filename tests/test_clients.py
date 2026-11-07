from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts import clients
from scripts.paid_media_rules import BudgetConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_CLIENTS = REPO_ROOT / "clients"


@pytest.fixture
def clients_dir(tmp_path: Path) -> Path:
    target = tmp_path / "clients"
    shutil.copytree(REPO_CLIENTS / "_template", target / "_template")
    return target


def test_every_committed_client_is_valid_with_loadable_budgets():
    found = clients.list_clients(REPO_CLIENTS)
    assert {c.slug for c in found} >= {"quantaroute", "managed-ai-finance-agent", "tradeshield-ai"}
    for c in found:
        cfg = BudgetConfig.load(c.budgets_path, currency=c.currency_symbol)
        assert cfg.currency == "£"


def test_own_products_are_marked_as_own_products_not_paying_clients():
    for slug in ("quantaroute", "managed-ai-finance-agent", "tradeshield-ai"):
        c = clients.load(slug, REPO_CLIENTS)
        assert c.relationship == "own-product"
        assert c.offer == "internal"


def test_template_is_excluded_from_listing(clients_dir: Path):
    assert clients.list_clients(clients_dir) == []


def test_create_copies_template_and_sets_identity(clients_dir: Path):
    c = clients.create("acme-plumbing", "Acme Plumbing", clients_dir)
    assert c.slug == "acme-plumbing"
    assert c.name == "Acme Plumbing"
    assert c.offer == "ad-waste-audit"
    assert c.status == "prospect"
    assert not (c.root / "README.md").exists()
    assert c.log_path == clients_dir / "acme-plumbing" / "logs" / "decisions.jsonl"
    assert [x.slug for x in clients.list_clients(clients_dir)] == ["acme-plumbing"]


def test_create_rejects_duplicates_and_bad_slugs(clients_dir: Path):
    clients.create("acme", "Acme", clients_dir)
    with pytest.raises(clients.ClientError, match="already exists"):
        clients.create("acme", "Acme again", clients_dir)
    for bad in ("Acme", "acme_ltd", "-acme", "acme-", ""):
        with pytest.raises(clients.ClientError):
            clients.create(bad, "Bad", clients_dir)


def test_unknown_client_error_lists_known_clients(clients_dir: Path):
    clients.create("acme", "Acme", clients_dir)
    with pytest.raises(clients.ClientError, match="known: acme"):
        clients.load("nope", clients_dir)


def _edit(clients_dir: Path, client_slug: str, changes: dict):
    path = clients_dir / client_slug / "client.json"
    raw = json.loads(path.read_text())
    for dotted, value in changes.items():
        node = raw
        *parents, leaf = dotted.split("__")
        for key in parents:
            node = node[key]
        node[leaf] = value
    path.write_text(json.dumps(raw))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("slug", "other", "must match folder name"),
        ("name", "  ", "name must not be empty"),
        ("currency", "XYZ", "currency"),
        ("stage", "huge", "stage"),
        ("branding__primary_color", "blue", "hex colour"),
        ("engagement__offer", "everything", "engagement.offer"),
        ("engagement__relationship", "friend", "engagement.relationship"),
        ("proof_points", "fastest ever", "list of strings"),
    ],
)
def test_validation_rejects_bad_fields(clients_dir: Path, field: str, value, message: str):
    clients.create("acme", "Acme", clients_dir)
    _edit(clients_dir, "acme", {field: value})
    with pytest.raises(clients.ClientError, match=message):
        clients.load("acme", clients_dir)


def test_cli_validate_and_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.chdir(tmp_path)
    shutil.copytree(REPO_CLIENTS / "_template", tmp_path / "clients" / "_template")
    assert clients.main(["new", "acme", "--name", "Acme"]) == 0
    assert clients.main(["validate"]) == 0
    assert clients.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "ok: 1 clients valid" in out
    assert "acme" in out


def test_client_data_folders_are_git_ignored():
    ignored = (REPO_ROOT / ".gitignore").read_text()
    for pattern in ("clients/*/data/", "clients/*/reports/", "clients/*/logs/"):
        assert pattern in ignored
