# Gotchas — Orca Remote Server

Real pitfalls (from Orca docs + runs). Read BEFORE any run (mandated by
README). Append new ones after each run via the operator — never mid-run.

**G1 — `127.0.0.1` / wildcard as the pairing address.**
Symptom: client can't connect or reaches itself. Cause: loopback works only
on the server; wildcards aren't dialable. Fix: restart/re-generate with the
reachable tailnet/LAN/tunnel address in `--pairing-address` / connection
address. Never ship `127.0.0.1` to another computer.

**G2 — Tailscale address missing from the picker.**
Both sides must be on the same tailnet and online. Fix: `tailscale status`
on the server, confirm the `100.x` IPv4, click refresh beside **Connection
address**.

**G3 — Protocol-version mismatch after updating one side.**
Symptom: incompatible-version / perpetual Disconnected. Fix: update Orca on
**both** server and client, then reconnect. Pin the verified versions in
`inventory.md`.

**G4 — Agent CLI works on the laptop, missing on the server.**
Remote sessions use the server's `PATH`/home/creds. Fix: install +
authenticate on the server (`orca account add --agent claude|codex`,
`orca account list` to confirm). The remote client disables Add account by
design.

**G5 — Desktop share AND `orca serve` running together.**
Symptom: flapping state, duplicate/confused pairing links. Fix: stop one —
exactly one host mode per machine.

**G6 — Server slept.**
Laptops-as-servers sleep by default. Fix: disable sleep / enable
wake-for-network on the server, or move the runtime to an always-on box.
Verify with a disconnect/reconnect cycle, not just a ping.

**G7 — Pairing link pasted into chat/logs/tickets.**
Treat as exposure: revoke the grant (**Shared Server Access** → trash),
generate a fresh link, hand it over privately, record rotation in
`notes.md`. Keep links in `executions/.../secrets/` only.

**G8 — LAN-only server followed the client out of the house.**
Symptom: worked at home, dead on hotel Wi-Fi. Fix: migrate to the Tailscale
row (re-serve with the tailnet address, update saved host address on
clients via **Edit host** — no re-pair needed for the token).

**G9 — Linux server terminals dead, files fine.**
Missing compiler toolchain for the relay's native modules. Fix: install
build tools per OS (§6 Phase 2), then reconnect.

**G10 — Stale terminal handles after a runtime restart.**
`orca` terminal handles are runtime-scoped. Fix: `orca terminal list --json`
and reacquire — don't assume the old handle means the process died (check
`hostScope` first).
