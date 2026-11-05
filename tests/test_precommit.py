import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / ".githooks" / "pre-commit"


@pytest.fixture
def repo(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    shutil.copy(HOOK, tmp_path / "hook")
    for tool in ("gitleaks", "trufflehog"):
        stub(tmp_path, tool)
    return tmp_path


def stub(repo, tool, exit_code=0):
    path = repo / ".tools" / "bin" / tool
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\nexit {exit_code}\n")
    path.chmod(0o755)


def run_hook(repo, env=None):
    return subprocess.run(["bash", str(repo / "hook")], cwd=repo, capture_output=True,
                          text=True, env=env)


def commit_check(repo, rel, content="hello\n"):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    subprocess.run(["git", "add", "-f", "--", rel], cwd=repo, check=True)
    return run_hook(repo).returncode


@pytest.mark.parametrize("rel", [
    "fleet/servers.yaml",
    "fleet/sub/servers.example.yaml",
    "vault/a b/clé.env",
    "logs/audit/x.jsonl",
    ".ops-wake.state",
    ".env",
    "app/.env.local",
    "a.key",
    "b.pem",
    "c.tfvars",
    "d.tfvars.json",
    "servers/web.yaml",
    "secrets/x",
])
def test_blocked_paths(repo, rel):
    assert commit_check(repo, rel) == 1


@pytest.mark.parametrize("rel", ["fleet/servers.example.yaml", ".env.example", "docs/a b.md"])
def test_allowed_paths(repo, rel):
    assert commit_check(repo, rel) == 0


@pytest.mark.parametrize("content", [
    "tskey-abc123\n",
    "+tskey-abc123\n",
    "AKIAABCDEFGHIJKLMNOP\n",
    "sk-ant-xyz\n",
    "ghp_abc\n",
    "-----BEGIN PRIVATE KEY-----\n",
])
def test_secret_content_blocked(repo, content):
    assert commit_check(repo, "notes.txt", content) == 1


def test_clean_file_allowed(repo):
    assert commit_check(repo, "notes.txt", "nothing here\n") == 0


@pytest.mark.parametrize("tool", ["gitleaks", "trufflehog"])
def test_missing_scanner_blocks(repo, tool):
    (repo / ".tools" / "bin" / tool).unlink()
    (repo / "notes.txt").write_text("nothing here\n")
    subprocess.run(["git", "add", "notes.txt"], cwd=repo, check=True)
    env = {"PATH": "/usr/bin:/bin"}
    result = run_hook(repo, env)
    assert result.returncode == 1
    assert "ops tools install" in result.stderr


@pytest.mark.parametrize("tool", ["gitleaks", "trufflehog"])
def test_scanner_finding_blocks(repo, tool):
    stub(repo, tool, exit_code=1)
    assert commit_check(repo, "notes.txt", "nothing here\n") == 1
