# 1.2 SIP in 60 seconds

> [!IMPORTANT]
> This handbook assumes SIP literacy at the protocol level. If it's been a while, this page is the minimum vocabulary needed to follow the architecture chapters. RFC 3261 is the canonical reference; below is the operator's-eye-view.

## Transactions

A **transaction** is one SIP request plus everything that replies to it: provisional responses, retransmissions, and exactly one final response. Two state machines drive it:

- **INVITE transaction** — three-way: `INVITE → (1xx)* → 2xx-or-failure → ACK`. The ACK closes it.
- **Non-INVITE transaction** — two-way: `REQUEST → (1xx)* → final response`. No transaction-level ACK.

Identified by `Via:branch + From:tag + Call-ID + CSeq`. The transaction layer in Kamailio (`tm`, chapter 6.1) tracks every in-flight transaction in shm.

## Dialogs

A **dialog** is the longer-lived peer relationship between two UAs, established by `INVITE`/2xx/ACK and torn down by `BYE`. Multiple transactions run inside one dialog: the setup INVITE, mid-dialog re-INVITEs (hold/resume, SDP renegotiation), UPDATE, REFER, the BYE.

Identified by `Call-ID + From-tag + To-tag` — the same triple on every in-dialog message. The dialog layer in Kamailio (`dialog`, chapter 6.2) sits on top of `tm` and ties transactions into one call.

## ACK — the trickiest message in SIP

ACK has **two different semantics** depending on what it's acknowledging. This is the single most surprising thing about SIP for newcomers.

| Acknowledged response | ACK called | Hop scope | New transaction? |
|---|---|---|---|
| 2xx (success) | **positive ACK** | End-to-end (UAC → UAS, **not** proxied at the tx layer) | **Yes — its own new transaction** |
| 3xx–6xx (failure) | **negative ACK** | Hop-by-hop (within the INVITE transaction) | **No — part of the INVITE transaction** |

Operational consequences for a proxy:

- **Positive ACK** bypasses the transaction layer entirely. A proxy that wants to see it must `record_route()` during the INVITE so the dialog's route set keeps the proxy on the in-dialog path; otherwise the ACK goes UAC→UAS directly.
- **Negative ACK** is consumed locally by `tm` as the closing edge of the INVITE transaction — it's how the transaction terminates cleanly without retransmission storms.

Forgetting the distinction is how proxies end up "losing" 2xx-ACKs and breaking in-dialog routing.

## Role of a proxy

A SIP **proxy** is a forwarder — receives requests, makes routing decisions, sends them along. RFC 3261 distinguishes:

- **Stateless proxy** — receives, decides, forwards. No state retained, no retransmission handling. Cheap and fast, but can't fork or recover failed branches.
- **Stateful proxy** — creates a transaction per forwarded request. Tracks branches, handles retransmission, can fork, can run `failure_route`, can intercept replies. Almost all production deployments.

What a proxy **does not do** (this is the line separating a proxy from a **B2BUA**):

- Originate dialogs on its own.
- Terminate dialogs by issuing its own BYE.
- Rewrite `Call-ID`, tags, or other dialog identifiers.
- Generate replies on behalf of the UAS (narrow exceptions like `100 Trying`).

Kamailio is a proxy. Out of the box it stays inside the proxy contract. Modules like `uac` and `topos` blur the line when configured — knowing when you've crossed it is on you.

## Where these concepts surface in the handbook

| Concept | Where |
|---|---|
| Transaction state in shm | [6.1 Transactions (`tm`)](16-tm-internals.md) |
| Retransmission timers and timer wheels | [6.1](16-tm-internals.md) |
| Dialog state machine | [6.2 Dialogs](17-dialogs.md) |
| Reply matching to transactions | [3.5 Forwarding and replies](11-forwarding.md) |
| Stateless vs stateful forwarding | [3.5](11-forwarding.md), [2.5 Sizing](06-sizing-and-tuning.md) |
| Forking / branches | [3.5](11-forwarding.md) |
| Proxy-vs-B2BUA boundary | [8.1 Topology hiding](19-topos.md), this chapter |

---

<p markdown="1" align="center">
  [← Table of contents](../) · [← 1.1 Introduction](01-introduction.md) · [Next: 2.1 Process model →](02-process-model.md)
</p>
