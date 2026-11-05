import ipaddress
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = ["fleet/*.example.yaml", "ops.config.example.yaml", "incidents/*.example.md"]
FILES = sorted({p for pat in PATTERNS for p in ROOT.glob(pat)})

RFC5737 = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]
ALLOWED_LOCAL = {"127.0.0.1", "0.0.0.0"}
ALLOWED_TLDS = ("example.com", "example.org", "example.net")

IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")
URL_HOST = re.compile(r"https?://([A-Za-z0-9.-]+)")
BARE_DOMAIN = re.compile(
    r"(?<![\w@/.-])((?:[A-Za-z0-9-]+\.)+(?:com|org|net|io|dev|app|co|uk|ai|cloud|xyz|info|me))\b"
)


def _domain_ok(domain: str) -> bool:
    d = domain.lower().rstrip(".")
    return d.endswith(ALLOWED_TLDS) or d.split(".")[-1] == "example"


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_only_synthetic_values(path):
    text = path.read_text()
    bad = []
    for ip in IPV4.findall(text):
        if ip in ALLOWED_LOCAL:
            continue
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if not any(addr in net for net in RFC5737):
            bad.append(ip)
    hosts = set(URL_HOST.findall(text)) | set(BARE_DOMAIN.findall(text))
    for host in hosts:
        if IPV4.fullmatch(host):
            continue
        if not _domain_ok(host):
            bad.append(host)
    assert not bad, f"non-synthetic values in {path.name}: {sorted(set(bad))}"


def test_example_files_exist_for_fleet():
    for name in ("servers", "sites", "services", "providers", "notify"):
        assert (ROOT / "fleet" / f"{name}.example.yaml").exists()
