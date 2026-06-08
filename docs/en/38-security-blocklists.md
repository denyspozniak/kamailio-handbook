# 9.3 Dynamic blocklists — apiban and ipban

> [!IMPORTANT]
> Most people meet this feature without ever choosing to. If you started from the stock `kamailio.cfg`, you are *already* running a dynamic blocklist — the default config greylists flooders on its own, with no module you'd recognise as "the blocklist." This chapter pulls that machinery into the open: first the self-expiring ban the stock config ships, then how you extend it with an external reputation feed so you also block IPs that have never hit *you* yet.

## The antiflood you already shipped

The stock config wires [9.2](37-security-modules.md)'s `pike` detector into an `htable`-backed ban set, and the whole thing is a handful of lines. First the table is declared:

```
modparam("htable", "htable", "ipban=>size=8;autoexpire=300;")
```

That's a named `htable` (cross-link: [8.3 htable](21-htable.md)) called `ipban` — a hash map in shared memory. The load-bearing parameter is `autoexpire=300`: every entry deletes itself 300 seconds after it was written. Nobody has to clean up. The ban *forgets*.

Then, in the request-init route (the stock config calls it `route[REQINIT]`, run near the top of `request_route`), two checks back to back:

```
# already banned? drop without spending anything else
if ($sht(ipban=>$si) != $null) {
    xdbg("request from blocked IP - $rm from $fu (IP:$si:$sp)\n");
    exit;
}
# not banned — let pike count this packet
if (!pike_check_req()) {
    xalert("ALERT: pike blocking $rm from $fu (IP:$si:$sp)\n");
    $sht(ipban=>$si) = 1;
    exit;
}
```

Read the order, because the order is the point. The `$sht(ipban=>$si)` lookup comes *first*: if the source IP (`$si`) is already a key in the table, the request is dropped immediately — before `sanity`, before parsing the rest, before any real work. Only sources that aren't already banned reach `pike_check_req()`, which counts the packet against that source's rate ([9.2](37-security-modules.md): return `1` not-blocked, `-1`/`-2` flooding). On a flood verdict the route writes `$sht(ipban=>$si) = 1` — that one assignment *creates the key*, which is what the lookup at the top will catch on the next packet — logs it once, and exits.

So the loop closes on itself: `pike` is the detector, the `ipban` table is the memory, the lookup is the enforcement, and `autoexpire` is the release. It is `htable` plus `pike` composed into a self-expiring blocklist, entirely inside Kamailio, with no external dependency and no DB. The first packet over the limit pays for a `pike` check; every subsequent packet from that source for the next five minutes costs a single hash lookup and a `drop`.

## Why a self-expiring htable, not a permanent ban

The tempting "fix" is to make the ban permanent — write the IP to a file or a DB and never let it back in. Don't, and `autoexpire` is the reason the stock config doesn't.

A source IP on the public internet is not a person. It is a NAT gateway, a carrier CGNAT pool, a corporate egress, a mobile APN — routinely shared by hundreds of legitimate users alongside whatever tripped your rate limit. Ban it forever and you eventually lock out a real customer who happens to sit behind the same address as a scanner, with no path back except a human noticing and editing a list. `autoexpire=300` makes the ban a *cooldown*, not a sentence: the flooder is shut out for five minutes, and a real client behind the same NAT is inconvenienced for at most five minutes, self-healing with zero operator involvement.

The cost of that mercy is honest: a determined attacker churns source IPs. They get banned, they rotate to a fresh address, your table fills with five-minute-old entries that the attacker has already abandoned. Per-source rate limiting answers "is *this* IP misbehaving *right now*" — it has no opinion on an IP it has never seen. Which is exactly the gap a reputation feed fills.

## apiban — borrowed reputation

[apiban](https://github.com/apiban/apiban) (apiban.org) is the usual way to close that gap, so be precise about what it is: a free external REST service that distributes a curated list of IP addresses *already caught attacking other operators* — collected through a network of SIP honeypots. You request an API key, you poll its endpoint over HTTPS, you get JSON back. **It is not a Kamailio module.** There is no `modparam("apiban", ...)`. It is a feed; how you act on the feed is your decision, and there are two layers to act at.

**(a) Kernel-level — the standalone client.** apiban ships clients in Go and bash, with iptables / nftables / `ipset` / fail2ban integrations, that poll the feed on a timer — typically a `crontab` entry every few minutes — and program the firewall: the iptables client maintains a dedicated `APIBAN` chain and adds each bad IP to it (`ipset`/nftables variants do the same with a kernel set). Once an address is in that set, packets from it are dropped by the kernel *before Kamailio ever parses them* — before `pike`, before the `ipban` lookup, before the SIP stack sees a byte.

**(b) In-route — feed pulled into an `htable`.** apiban gives you no Kamailio client for this; you build it. Poll the same JSON feed from inside Kamailio with `http_client` on an `rtimer` clock, and write each returned IP into an `htable` — conceptually the same `ipban` table from above, just populated from the feed instead of from `pike`. Then your existing `$sht(...)` check in `route[REQINIT]` blocks feed IPs and locally-detected flooders with the same line. The block now happens *inside* Kamailio, after parse.

The tradeoff between the two is the tradeoff of the whole chapter: kernel-level is cheaper per packet (a dropped packet never costs you a SIP parse) but blunt — it's a yes/no firewall verdict with no SIP context. In-route is more expensive (you parse before you decide) but flexible — you can log per route, exempt an authenticated user, treat a feed hit as "challenge harder" rather than "drop," and reuse the same table for both feed and local detection.

## Where to block: kernel vs. route

| Layer | Per-packet cost | Flexibility | Use it for |
|---|---|---|---|
| Kernel — `ipset`/nftables/iptables (apiban client) | Lowest — drop before the SIP stack parses anything | Low — pure IP yes/no, no SIP context | Blunt volume: known-bad reputation feeds, obvious flood IPs you never want to reason about |
| In-Kamailio — `ipban` `htable` + `pike` | A hash lookup per packet, after parse | High — per-route decisions, logging, "challenge not drop," shared via `dmq` | Behaviour-driven greylisting: your own `pike` verdicts, anything where the *decision* depends on SIP context |

The two are complements, not rivals. Push the high-volume, no-judgement-needed reputation list down to the kernel where each drop is nearly free; keep the behaviour-driven greylist — the part that earned its bans by watching *your* traffic — in Kamailio where you have context. And if you run more than one instance, the `ipban` table is exactly the kind of state [8.5 dmq](23-dmq.md) replicates: detect a flooder on one node, ban it across the cluster.

Either way, the job of this whole chapter is to keep junk from reaching the part of your config that actually does work — which matters most for the traffic that *isn't* a flood. The scanners that probe quietly, one well-formed request at a time, are the ones carrying the payload [9.4](39-security-fuzzing-rce.md) is about. A reputation feed that has already seen them elsewhere is your cheapest defence against them arriving here.

---

<p markdown="1" align="center">
  [← Table of contents](../) · [← 9.2 Defensive modules](37-security-modules.md) · [Next: 9.4 Fuzzing & RCE →](39-security-fuzzing-rce.md)
</p>
