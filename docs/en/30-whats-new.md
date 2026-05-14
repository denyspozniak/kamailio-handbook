# 9.3 What's new — and what's in development

> [!IMPORTANT]
> The handbook targets **Kamailio 6.1.x** (April 2026 stable line). This appendix lists the headline changes between recent major versions, what was archived along the way, and where to look for what's happening on the development branch. It is intentionally a *pointer* — the wiki and the source repo are the authoritative trackers.

## Quick orientation across recent versions

| Branch | Status (May 2026) | First release | What it brought |
|---|---|---|---|
| 6.1.x | **Current stable** | 2026-03-03 | 4 new modules, VRF in core, TLS domain match, SHA3 transformations, new RPCs |
| 6.0.x | Maintained | 2025 | First 6.x line — multi-threaded UDP receiving, CMake build system, removed 8 legacy modules |
| 5.8.x | Maintained (long-tail) | 2024 | Last 5.x; many production deployments still here |
| `master` (devel) | → 6.2.x | — | Active development; see GitHub repo for in-progress work |

Kamailio doesn't have a formal "LTS" designation — each `X.Y` line is maintained for roughly a year past the next major's release. In practice operators target either the current stable (6.1.x for new deployments) or one line back (6.0.x) for conservatism.

## What 6.1.x added

**New modules**

| Module | Purpose |
|---|---|
| `auth_arnacon` | Authentication via the Arnacon protocol |
| `auth_web3` | Web3-style authentication support (wallet-based identity) |
| `peerstate` | Track peer state across the cluster, complementing dispatcher liveness |
| `ptimer` | Process-level timers — more granular timer scheduling than the global `timer` |

**Modules archived (moved to `kamailio-archive` repo)**

- `app_java`, `db_berkeley`, `db_perlvdb` — long-unused integrations that no longer justified the maintenance overhead.

**Notable core changes**

- **VRF (Virtual Routing and Forwarding)** support in core socket definitions — bind listeners into specific Linux VRFs.
- **TLS connection domain matching** — select TLS config per-connection by SNI / SAN matching.
- **SHA3 / Keccak** cryptographic transformations available to the cfg DSL.
- New pseudo-variables `$defv()`, `$defs()`, `$iuid` — runtime access to defined values and a per-instance UUID.
- RPC commands `modparam.getn`, `modparam.setn`, `modparam.list` — proper introspection and runtime tweaking of module parameters (chapter 2.4 covered the `cfg.*` family; these are a generalisation).
- TCP listen backlog now configurable, useful for accept-storm protection.
- ARM64 platform support improvements — Kamailio runs cleanly on graviton-class instances.

## What 6.0.x changed (vs 5.x)

This is the bigger break. If your team is still on 5.8.x and considering the jump, this is where to focus:

**Architectural changes**

- **Multi-threaded UDP receiving** as an option — the worker process model (chapter 2.1) gets a hybrid mode where one process can use multiple threads for UDP `recvfrom`. Doesn't replace the per-message-per-worker pattern but reduces total process count for very high-PPS scenarios.
- **CMake build system** — replaces the old hand-rolled Makefile build. New build invocations: `cmake -S . -B build && cmake --build build`. Old `make` workflow still works but CMake is now the recommended path.
- **TLS migrated from OpenSSL ENGINE to provider keys** for OpenSSL 3.x compatibility. Affects custom TLS configs that referenced ENGINE keys.

**Modules archived in 6.0.x**

- `auth_identity`, `app_lua_sr`, `app_sqlang`, `app_mono` — obsolete scripting bridges (Lua now via `app_lua`, Python via `app_python3`, etc.).
- `db_cassandra` — superseded by mainstream DB modules; Cassandra integrations now via external pipelines.
- `osp`, `print`, `print_lib` — long-deprecated.

**Breaking config changes**

- `dialog` dropped support for the old `dlg_flag` parameter — set state via `dlg_manage()` flags instead.
- `app_python3` removed legacy compatibility shims; scripts targeting Kamailio 5.x may need minor tweaks.

## What's in development (`master` branch)

The `master` branch on [github.com/kamailio/kamailio](https://github.com/kamailio/kamailio) is where 6.2.x is taking shape. The wiki page [kamailio.org/wikidocs/features/new-in-devel/](https://www.kamailio.org/wikidocs/features/new-in-devel/) is the authoritative running list — it gets updated by the maintainers as features land.

How to read what's coming without that page:

```bash
# Recent commits to master
gh repo clone kamailio/kamailio && cd kamailio
git log --oneline master --since="3 months ago" | head -50

# New modules in master vs latest stable tag
git diff --name-status 6.1.2..master -- src/modules/ | grep '^A' | head -20

# Open PRs labelled "feature"
gh pr list --repo kamailio/kamailio --label feature --state open
```

The mailing list `sr-dev@lists.kamailio.org` carries the design discussions before code lands; the GitHub Discussions tab is where high-level direction questions get debated.

## How handbook chapters relate to versioning

This handbook targets Kamailio 6.1.x and the architectural concepts are stable across recent versions. Specific things to watch when reading older chapters against a different version:

- **Process model** (chapter 2.1) — adds the optional UDP-receiving threading mode in 6.0+, but the multi-process discipline is unchanged.
- **Memory** (chapter 2.2) — allocator choice and the `pkg`/`shm` split are unchanged since well before 5.x.
- **Lumps** (chapter 3.3) — the data-lump machinery has been stable for 15+ years. Source files still `data_lump.{c,h}`.
- **KEMI** (chapter 5) — the `KSR.*` API is forward-compatible; new bindings get added per-release without removing old ones.
- **Routing engine** (chapter 3.4) — `reply_route` and `onreply_route` both exist in every modern version; the available events for `event_route[…]` grow with each release as modules add hooks.
- **`htable`, `dispatcher`, `dmq`** (chapter 8) — feature surface grows; the architectural patterns described are unchanged.

If you encounter behaviour that contradicts the handbook on a current version, **the source repo wins** — the handbook is best-effort but the C code is authoritative.

## Where to follow Kamailio development

- **GitHub repo**: [kamailio/kamailio](https://github.com/kamailio/kamailio) — code, issues, PRs.
- **Wiki**: [kamailio.org/wikidocs](https://www.kamailio.org/wikidocs/) — features-per-version pages, module docs.
- **Mailing lists**: `sr-users@` for ops questions, `sr-dev@` for development.
- **Asipto blog** ([asipto.com](https://www.asipto.com/blog/)) — the company behind much of Kamailio's commercial development; posts about new features and roadmap.
- **The annual KamailioWorld conference** — release recaps and roadmap talks.

---

<p markdown="1" align="center">
  [← Table of contents](../) · [← 9.2 Term map](28-term-map.md)
</p>
