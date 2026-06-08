# 9.2 Defensive modules — what each one actually checks

> [!IMPORTANT]
> [9.1](36-security-surface.md) ended on one rule: filter cheap and early, authenticate the rest. These are the modules that filter, and each checks exactly one thing — `sanity` proves the message is legal SIP, `secfilter` matches strings against lists, `pike` counts packets per source, `auth` establishes who sent it. None inspects free-text header *content* for shell or SQL safety. Knowing which does what is the whole game.

## `sanity` — well-formedness, not safety

`sanity_check([msg_checks[, uri_checks]])`, called first in `request_route` as `route("sanity")`, answers one question: *is this legal SIP?* On failure `sanity_reply()` emits the matching `4xx`. The documented checks are all structural — R-URI version and scheme, required headers (`To`/`From`/`CSeq`/`Call-ID`/`Via`), `CSeq` method-matches-request and a valid integer, **`Content-Length` equal to the actual body size** (the one that catches truncation and request smuggling), `Expires` value, Proxy-Require, parseable URIs, digest-credential form, duplicated To/From tags, a present-parseable-branched first `Via`, and RFC 3261 magic-cookie/`lr` compliance.

Every check is about *form*, never *meaning* — the pivot for [9.4](39-security-fuzzing-rce.md):

> A `$(...)` substring inside a `User-Agent`, or a `'` inside a `From`, is legal SIP token content. `sanity_check()` passes it untouched.

`sanity` rejects a packet whose `Content-Length` lies about its body; it cannot reject a well-formed packet that smuggles a shell metacharacter or an SQL fragment, because that packet is *valid SIP*. It is a syntax gate — cheap triage against malformed junk, and nothing about hostile-but-well-formed content.

## `secfilter` — the content filter

`secfilter` is the stock set's closest thing to content filtering: in-memory black/whitelists (loaded from DB), matched by a `secf_check_*` family.

| Function | Matches |
|---|---|
| `secf_check_ip()` | source IP vs blacklist |
| `secf_check_ua()` | `User-Agent` vs UA list |
| `secf_check_from_hdr()` / `secf_check_to_hdr()` | `From`/`To` user, domain, display-name |
| `secf_check_contact_hdr()` | `Contact` user / domain |
| `secf_check_dst(string)` | destination number |
| `secf_check_country(string)` | country code (needs `geoip`) |
| `secf_check_sqli_hdr(string)` / `secf_check_sqli_all()` | illegal chars in one value / across UA, From, To, Contact |

This catches `friendly-scanner` UAs, known-bad domains, toll-fraud prefixes, and obvious SQLi probes. But it is **static pattern matching** — strings and a fixed illegal-character set. It raises the cost of a naive attack; it has no idea what your downstream DB, shell, or script does with a value. A filter, not a guarantee — and the wrong layer for [9.4](39-security-fuzzing-rce.md)-style safety, which must happen where you *use* the value.

## `pike` — flood detection

`pike` answers *is one source sending too fast?* It tracks per-source-IP rate in shm via a tree keyed byte-by-byte on the address (one structure spans IPv4 and IPv6). `pike_check_req()` — or `pike_check_ip(ipaddr)` for an arbitrary address — accounts each hit. Three params set policy: `sampling_time_unit` (window seconds, default `2`), `reqs_density_per_unit` (allowed per window, default `30`), `remove_latency` (idle retention, default `120`).

The return is the point: `1` not-blocked (also on internal error — fail-open), `-1` known flooder, `-2` *new* flooder this instant. The `-2`/`-1` split lets you act once on first detection (log, ban) then short-circuit every later packet from that source. That verdict normally feeds the `ipban` pattern of [9.3](38-security-blocklists.md): `pike` detects, the `htable` remembers.

## `topoh` / `topos` — cut the recon

Not filters — topology hiding, read here as reconnaissance denial. A scanner mines `Via`, `Record-Route`, `Contact`, and `Route` to map your internal addressing; `topoh` (encodes or strips those headers) and `topos` (stashes the state server-side, hands back an opaque token) shrink what leaks in the replies you *do* send. Mechanics are in [8.1 topology hiding](19-topos.md); they sit here because edge hardening is as much about what you leak in replies as what you accept in requests.

## `auth` — the only real trust boundary on UDP

Everything above is heuristic — none establishes *who* sent the packet, and on UDP source IP is not identity ([9.1](36-security-surface.md)). `auth` draws the identity boundary via SIP digest. The challenge functions — `www_challenge(realm, flags[, algorithms])` (`401`, registrar/UAS), `proxy_challenge(...)` (`407`, proxy), `auth_challenge(...)` (picks by context) — emit the `WWW-`/`Proxy-Authenticate` header; the verify side (`pv_www_authenticate` / `pv_proxy_authenticate` / `pv_auth_check`) recomputes the digest against the stored secret and accepts only on a match. Replay protection lives in the challenge: bounded nonce lifetime (`nonce_expire`, default `300`s), and `qop` brings in the client nonce-count so a captured `Authorization` can't be replayed. This — not any blacklist — stops the REGISTER-hijack and toll-fraud cases. Filtering buys cheap rejection of garbage; only `auth` lets you trust what's left.

## Summary

| Module | Checks | Where | Does *not* |
|---|---|---|---|
| `sanity` | SIP well-formedness | first in `request_route` | inspect content for shell/SQL safety |
| `secfilter` | fields vs lists; SQLi char set | early, per request | parse intent; catch anything off-list |
| `pike` | request rate per source IP | per request, edge | care about content or identity |
| `topoh`/`topos` | (rewrites outbound state) | per message, edge | reject requests; authenticate |
| `auth` | digest identity of the sender | after cheap filters | filter floods or malformed input |

Top to bottom, that is the [9.1](36-security-surface.md) doctrine made concrete: reject malformed junk for almost nothing (`sanity`), drop known-bad strings and floods (`secfilter`, `pike`), leak little in replies (`topoh`/`topos`), and spend a digest challenge (`auth`) only on traffic that survived. The gap it exposes: `pike` forgets a flooder after `remove_latency`, and `secf_check_ip()` only matches a list you populate. Turning one-off detection into a durable, shareable, cluster-wide ban is [9.3](38-security-blocklists.md).

---

<p markdown="1" align="center">
  [← Table of contents](../) · [← 9.1 Attack surface](36-security-surface.md) · [Next: 9.3 Dynamic blocklists →](38-security-blocklists.md)
</p>
