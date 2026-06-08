# 9.2 Defensive modules — what each one actually checks

> [!IMPORTANT]
> [9.1](36-security-surface.md) ended on one rule: filter cheap and early, authenticate the rest. These are the modules that do the filtering — the cheap, early checks that let you reject before you pay full processing cost. The thing to keep straight while reading: each one checks exactly one thing, and it checks it well. None of them sanitizes free-text header *content* for shell or SQL safety unless you explicitly ask it to — and most can't even do that. `sanity` proves the message is legal SIP; `secfilter` matches strings against lists; `pike` counts packets per source; `auth` is the only one that establishes who sent it. Knowing which is which is the whole game.

## `sanity` — well-formedness, not safety

`sanity` answers one question: *is this a legal SIP message?* You call `sanity_check([msg_checks [, uri_checks]])` — by convention as the very first thing in `request_route`, wrapped in `route("sanity")` ([9.1](36-security-surface.md) put it there) — and on failure it can emit the matching `4xx` itself via `sanity_reply()`.

The check set is structural. The documented checks include:

- **ruri sip version** and **ruri scheme** — the request URI uses a SIP version Kamailio handles and a scheme it supports (`sip[s]`/`tel[s]`).
- **required headers** — `To`, `From`, `CSeq`, `Call-ID`, `Via` are all present.
- **CSeq method** and **CSeq value** — the `CSeq` method matches the request method, and its number is a valid unsigned integer.
- **content length** — the actual body size matches the `Content-Length` value. This is the one that catches a lot of truncation and smuggling games.
- **expires value**, **proxy require**, **parse uri's**, **digest credentials**, **duplicated To/From tags**, **first Via header** (present, parseable, has a branch), and **RFC3261 compliance** (magic-cookie branch prefix, `lr` param).

Every one of those is a question about *form*. None is a question about *meaning*. And that distinction is the pivotal point for [9.4](39-security-fuzzing-rce.md):

> `sanity` validates that the message is legal SIP. A `$(...)` substring sitting inside a `User-Agent` header is a perfectly legal SIP token — it is well-formed text in a header that is allowed to contain arbitrary text. So `sanity_check()` passes it through untouched.

`sanity` will reject a packet whose `Content-Length` lies about its body. It will not, and cannot, reject a packet that smuggles a shell metacharacter or an SQL fragment into a header value, because that packet is *valid SIP*. Treat `sanity` as a syntax gate: it stops malformed and truncated junk early and cheaply, and it does nothing about hostile-but-well-formed content. The latter is [9.4](39-security-fuzzing-rce.md)'s problem.

## `secfilter` — the content filter

`secfilter` is the closest thing in the stock module set to application-content filtering. It holds blacklists and whitelists (in memory, loaded from a DB) and exposes a `secf_check_*` family that matches message fields against them:

| Function | What it matches |
|---|---|
| `secf_check_ip()` | source IP against the IP blacklist |
| `secf_check_ua()` | `User-Agent` against the UA blacklist |
| `secf_check_from_hdr()` | `From` user / domain / display-name against their lists |
| `secf_check_to_hdr()` | same, for `To` |
| `secf_check_contact_hdr()` | `Contact` user / domain |
| `secf_check_dst(string)` | destination number against the blacklist |
| `secf_check_country(string)` | country code (needs `geoip`) |
| `secf_check_sqli_hdr(string)` | illegal characters in a single given value |
| `secf_check_sqli_all()` | illegal characters across `User-Agent`, `From`, `To`, and `Contact` |

So this is where you catch the `friendly-scanner` user-agents, the known-bad source domains, the toll-fraud destination prefixes — and, with `secf_check_sqli_all()`, the obvious SQL-injection probes hiding in those four headers.

But know its limits. It is **static pattern matching**, not a sandbox and not a parser. The blacklists are strings and the SQLi check is a fixed set of illegal characters — it raises the cost of a naive attack, it does not understand what your downstream consumer (a DB, a shell, a script) will do with the value. It catches what you told it to catch. It is a filter, not a guarantee, and it is the wrong layer to rely on for [9.4](39-security-fuzzing-rce.md)-style content safety — that has to happen where you actually use the value.

## `pike` — flood detection

`pike` answers a different question entirely: *is one source sending too fast?* It tracks request rate **per source IP** in shared memory, using a tree keyed byte-by-byte on the address (one structure covers both IPv4 and IPv6, expanding as new sources appear). You call `pike_check_req()` (or `pike_check_ip(ipaddr)` to check an arbitrary address) on each request, and it accounts that hit against the source.

Three parameters set the policy:

- `sampling_time_unit` — the sampling window, in seconds (default `2`).
- `reqs_density_per_unit` — requests allowed per window before the source is treated as flooding (default `30`).
- `remove_latency` — how long an idle source is kept in memory after its last packet (default `120`).

The return value is the whole point: `1` means *not blocked* (or an internal error — fail-open), `-1` means *known flooder, already detected*, and `-2` means *new flooder, first detection this instant*. The `-2`/`-1` split lets you act once on first detection (log it, add to a blocklist) and then cheaply short-circuit every subsequent packet from the same source.

That return is normally wired straight into the `ipban` pattern: on a flood verdict you push the source into an `htable`-backed ban set and `drop` it for a while — the mechanism [9.3](38-security-blocklists.md) is built around. `pike` is the detector; the blocklist is the memory.

## `topoh` / `topos` — cut the recon

`topoh` and `topos` aren't filters — they're topology hiding, and the security payoff here is reconnaissance denial. A scanner reads `Via`, `Record-Route`, `Contact`, and `Route` to map your internal addressing and infer your stack. Topology hiding mangles or strips that information so the bytes leaving your edge reveal far less about what's behind it ([9.1](36-security-surface.md)'s OPTIONS/UA recon row, defanged). It doesn't reject anything; it shrinks what an attacker learns from the traffic you *do* answer.

The mechanics — `topoh` rewriting headers with an encoded value versus `topos` stashing the full state server-side and handing back an opaque token — are covered in [8.1 topology hiding](19-topos.md). It is listed here only so the security picture is complete: hardening the edge is as much about *what you leak in replies* as about *what you accept in requests*.

## `auth` — the only real trust boundary on UDP

Everything above is heuristic. `sanity` guesses at well-formedness, `secfilter` matches strings, `pike` counts. None of them establishes *who* sent the packet — and on UDP ([9.1](36-security-surface.md)) the source IP is not an identity. `auth` is the one module that draws an actual identity boundary, via SIP digest.

The challenge functions are the gate:

- `www_challenge(realm, flags [, algorithms])` — emits a `WWW-Authenticate` header and the `401` reply (the end-user / registrar case).
- `proxy_challenge(realm, flags [, algorithms])` — emits a `Proxy-Authenticate` header and the `407` reply (the proxy case).
- `auth_challenge(realm, flags [, algorithms])` — picks `401` vs `407` based on context.

The verification side (`pv_www_authenticate` / `pv_proxy_authenticate` / `pv_auth_check`) recomputes the digest against the stored secret and accepts only if it matches. The replay protection lives in the challenge: nonces have a bounded lifetime (`nonce_expire`, default `300`s), and enabling `qop` brings in the client nonce-count so a captured `Authorization` header can't simply be replayed. This — not any blacklist — is what stops the REGISTER-hijack and toll-fraud cases from [9.1](36-security-surface.md). Filtering buys you cheaper rejection of garbage; only `auth` lets you trust the traffic that's left.

## Summary

| Module | What it checks | Where it runs | What it does *not* do |
|---|---|---|---|
| `sanity` | SIP syntax / well-formedness | first thing in `request_route`, per request | inspect header *content* for shell/SQL safety |
| `secfilter` | fields vs blacklists/whitelists; SQLi char set | early, per request | parse intent; sandbox; catch anything not on a list |
| `pike` | request rate per source IP | per request, at the edge | care about content or identity — just rate |
| `topoh`/`topos` | (nothing — rewrites outbound state) | per message, edge | reject requests; authenticate |
| `auth` | digest identity of the sender | per request, after cheap filters | filter floods or malformed input |

Read top to bottom that table is the [9.1](36-security-surface.md) doctrine made concrete: reject malformed junk for almost nothing (`sanity`), drop known-bad strings and floods next (`secfilter`, `pike`), reveal little in your replies (`topoh`/`topos`), and spend real CPU on a digest challenge (`auth`) only for traffic that survived the cheap stages.

The gap the table makes obvious: `pike` detects a flooder but doesn't *remember* it past `remove_latency`, and `secf_check_ip()` only matches a list you have to populate. Turning a one-off detection into a durable, shareable ban — and doing it across a cluster — is [9.3](38-security-blocklists.md).

---

<p markdown="1" align="center">
  [← Table of contents](../) · [← 9.1 Attack surface](36-security-surface.md) · [Next: 9.3 Dynamic blocklists →](38-security-blocklists.md)
</p>
