# 9.3 Dynamic blocklists — apiban and ipban

> [!IMPORTANT]
> If you started from the stock `kamailio.cfg`, you are *already* running a dynamic blocklist — the default config greylists flooders with no module you'd recognise as "the blocklist." This chapter opens that machinery: the self-expiring ban the stock config ships, then how an external reputation feed extends it to IPs that have never hit *you* yet.

## The antiflood you already shipped

The stock config wires [9.2](37-security-modules.md)'s `pike` into an `htable`-backed ban set in a handful of lines. The table:

```
modparam("htable", "htable", "ipban=>size=8;autoexpire=300;")
```

A named `htable` ([8.3 htable](21-htable.md)) `ipban`, a hash map in shm. The load-bearing param is `autoexpire=300`: every entry self-deletes 300 s after it's written — nobody cleans up, the ban *forgets*. Then, in `route[REQINIT]` (near the top of `request_route`), two checks back to back:

```
if ($sht(ipban=>$si) != $null) {     # already banned? drop, spend nothing else
    exit;
}
if (!pike_check_req()) {             # not banned — let pike count this packet
    $sht(ipban=>$si) = 1;            # flood verdict → create the key
    exit;
}
```

The order *is* the mechanism. The `$sht(ipban=>$si)` lookup runs first — a banned `$si` is dropped before `sanity`, before the rest of the parse, before any real work. Only unbanned sources reach `pike_check_req()` ([9.2](37-security-modules.md): `1` ok, `-1`/`-2` flooding); a flood verdict writes `$sht(ipban=>$si) = 1`, and *that assignment is the ban* — the next packet hits the top lookup and dies. `pike` detects, `ipban` remembers, the lookup enforces, `autoexpire` releases — `htable` + `pike` composed into a self-expiring blocklist with no external dependency and no DB. The first over-limit packet pays for a `pike` check; every later one for the next 300 s costs a hash lookup and a `drop`.

## Why self-expiring, not permanent

A public source IP is not a person — it's a NAT gateway, a CGNAT pool, a corporate egress, a mobile APN, shared by hundreds of legitimate users alongside whatever tripped your limit. A permanent ban eventually locks out a real customer behind the same address as a scanner, with no recovery but a human editing a list. `autoexpire=300` makes the ban a *cooldown*: the flooder is shut out for five minutes, a real client behind the same NAT waits at most five, self-healing with zero operator involvement. The honest cost: a determined attacker rotates source IPs, and your table fills with five-minute-old entries it has already abandoned. Per-source rate limiting answers "is *this* IP misbehaving *now*" — it has no opinion on an IP it has never seen. That gap is what a reputation feed fills.

## apiban — borrowed reputation

[apiban](https://github.com/apiban/apiban) (apiban.org) is a free external REST service distributing a curated list of IPs *already caught attacking other operators*, collected via a network of SIP honeypots. You request an API key and poll its HTTPS endpoint for JSON. **It is not a Kamailio module** — there is no `modparam("apiban", ...)`. It is a feed; you choose where to act on it.

- **Kernel — the standalone client.** apiban ships Go and bash clients with iptables / nftables / `ipset` / fail2ban integrations that poll on a `crontab` timer and program the firewall (the iptables client maintains a dedicated `APIBAN` chain). Packets from a listed IP are dropped by the kernel *before Kamailio parses a byte* — before `pike`, before the `ipban` lookup.
- **In-route — feed pulled into an `htable`.** No Kamailio client exists for this; you build it: poll the same JSON with `http_client` on an `rtimer` clock and write each IP into an `htable` — the same `ipban` table, populated from the feed instead of `pike`. Your existing `$sht(...)` check then blocks feed IPs and locally-detected flooders with one line, now *after* parse.

| Layer | Per-packet cost | Flexibility | Use it for |
|---|---|---|---|
| Kernel — `ipset`/nftables/iptables (apiban client) | lowest — drop before any SIP parse | low — pure IP yes/no, no SIP context | blunt volume: reputation feeds, obvious flood IPs |
| In-Kamailio — `ipban` `htable` + `pike` | a hash lookup, after parse | high — per-route logic, "challenge not drop", `dmq`-shared | behaviour-driven greylisting; decisions needing SIP context |

Complements, not rivals: push the high-volume, no-judgement reputation list to the kernel where each drop is nearly free; keep the behaviour-driven greylist — the bans your own traffic earned — in Kamailio where you have context. Across instances, `ipban` is exactly the state [8.5 dmq](23-dmq.md) replicates: detect a flooder on one node, ban it cluster-wide. And the quiet scanners that probe one well-formed request at a time carry the payload of [9.4](39-security-fuzzing-rce.md) — a feed that already saw them elsewhere is your cheapest defence against them landing here.

---

<p markdown="1" align="center">
  [← Table of contents](../) · [← 9.2 Defensive modules](37-security-modules.md) · [Next: 9.4 Fuzzing & RCE →](39-security-fuzzing-rce.md)
</p>
