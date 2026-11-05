import json
import subprocess
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "guard.sh"


def guard(command):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run(["sh", str(GUARD)], input=payload, capture_output=True, text=True,
                          cwd=GUARD.parent).returncode


@pytest.mark.parametrize("command", [
    "git commit --no-verify -m x",
    "git commit -nm x",
    "git commit -m x -n",
    "git -C . commit -n",
    "cd x && git commit -n -m y",
    "GIT_X=1 git commit -n",
    "git commit -m x --no-ver",
    "sh -c 'git commit -n'",
    'bash -c "git commit --no-verify"',
    "command git commit -n",
    "env git commit -n",
    "/usr/bin/git commit -n",
    "if true; then git commit -n; fi",
    "git config core.hooksPath /dev/null",
    "git -c core.hooksPath=/x commit -m y",
    "git push origin master",
    "git push origin HEAD:master",
])
def test_blocked(command):
    assert guard(command) == 2


@pytest.mark.parametrize("command", [
    "git commit -m x",
    'git commit -m "fix -n flag"',
    "git commit -am msg",
    "git commit --no-edit",
    "git commit -m x --no-gpg-sign",
    "git commit -F msg.txt",
    "echo git commit --no-verify",
    'echo "git commit -n"',
    "git log -n 5",
    "git config --get core.hooksPath",
    "git push origin feature",
    "ls",
])
def test_allowed(command):
    assert guard(command) == 0


def test_malformed_input_is_not_blocked():
    proc = subprocess.run(["sh", str(GUARD)], input="garbage", capture_output=True, text=True)
    assert proc.returncode == 0
