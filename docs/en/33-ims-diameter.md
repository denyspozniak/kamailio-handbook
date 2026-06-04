# 10.3 The Diameter side

> [!IMPORTANT]
> SIP carries the call. **Diameter** carries everything the call *depends on* — who the subscriber is, whether they're allowed, what QoS their media gets, and what it costs. A CSCF that can't speak Diameter is a proxy that can register nobody and authorise nothing. So alongside its SIP stack, Kamailio runs a full Diameter peer — and understanding that peer is half of understanding Kamailio-in-IMS.

## Why IMS needs a second protocol at all

SIP is a session protocol; it has no business knowing your subscription tier, your authentication vectors, or your prepaid balance. 3GPP put all of that on **Diameter** (RFC 6733), an AAA protocol with a request/answer command model, structured **AVPs** (Attribute-Value Pairs), and persistent peer connections. Every Diameter link in IMS is one of the reference points from [10.1](31-ims-overview.md): Cx to the HSS, Rx to the PCRF, Ro/Rf to the charging system.

## `cdp` — the C Diameter Peer

Kamailio's Diameter stack is the **`cdp`** module (C Diameter Peer), with `cdp_avp` providing typed helpers for reading and building AVPs. `cdp` is loaded once and **shared** by all the IMS modules that need Diameter — `ims_icscf`, `ims_registrar_scscf`, `ims_auth`, `ims_qos`, `ims_charging` all call into it rather than each opening their own connection.

Key properties:

- **Persistent peers.** `cdp` maintains long-lived connections to each Diameter peer (HSS, PCRF, OCS, or a DRA in front of them), with its own connection state machine: it does the Capabilities-Exchange (CER/CEA) handshake on connect and Device-Watchdog (DWR/DWA) keepalives to detect dead peers.
- **Config in XML.** Unlike most Kamailio config, `cdp` is configured by an external XML file (realm, peer list, transport, AVP dictionaries) referenced from the cfg. This is OpenIMSCore heritage.
- **Async by nature.** A Diameter round-trip happens *inside* SIP processing — the S-CSCF can't answer the REGISTER until the MAA comes back. The IMS modules use Kamailio's async/transaction-suspend machinery (see [8.2 Async transactions](20-async-transactions.md)) so a worker isn't blocked on the wire waiting for the HSS.

## What Kamailio speaks, and on which module

| Interface | Kamailio side | Peer | What it does |
|---|---|---|---|
| **Cx** | `ims_icscf`, `ims_registrar_scscf`, `ims_auth` | HSS | Auth, S-CSCF selection, profile/iFC download |
| **Rx** | `ims_qos` | PCRF / PCF | Authorise media, request a dedicated bearer with QoS |
| **Ro** (online) / **Rf** (offline) | `ims_charging` | OCS / CHF | Credit control: reserve units, debit, release |

### Command codes you'll meet

Cx (HSS):

| Code | Command | Trigger |
|---|---|---|
| 300 | **UAR**/UAA — User-Authorization | I-CSCF on REGISTER |
| 303 | **MAR**/MAA — Multimedia-Auth | S-CSCF fetching the auth vector |
| 301 | **SAR**/SAA — Server-Assignment | S-CSCF registering itself + pulling iFC |
| 302 | **LIR**/LIA — Location-Info | I-CSCF on a terminating call |
| 304 | **RTR**/RTA — Registration-Termination | HSS pushing a deregistration to the S-CSCF |
| 305 | **PPR**/PPA — Push-Profile | HSS pushing a profile update |

Rx (PCRF), Ro (OCS):

| Code | Command | Trigger |
|---|---|---|
| 265 | **AAR**/AAA — AA-Request | P-CSCF authorising media for a session |
| 275 | **STR**/STA — Session-Termination | P-CSCF tearing the media authorisation down |
| 274 | **ASR**/ASA — Abort-Session | PCRF aborting a session |
| 272 | **CCR**/CCA — Credit-Control | S-CSCF reserving/debiting charging units |

> [!NOTE]
> When the network multi-homes its HSS, the I/S-CSCF first asks an **SLF** (Subscription Locator Function) which HSS holds a given user — the SLF answers with a Diameter Redirect (the **Dx** reference point). In practice this job is increasingly handed to a **DRA** (Diameter Routing Agent) that proxies Cx to the right HSS; the CSCF just points `cdp` at the DRA. More on the DRA in [10.4](34-ims-full-solution.md).

## What kills you

- **Peer flapping.** If the HSS/DRA connection drops, `cdp` tears down and retries — and during that window every REGISTER fails (no MAA). Watch the CER/DWR state; a peer that's silent on watchdogs is about to take your registrations down with it.
- **AVP dictionary mismatch.** `cdp` only understands the AVPs in its loaded dictionaries. A peer (HSS/PCRF) that sends a vendor-specific AVP `cdp` doesn't know about gets that AVP dropped or the message rejected — and the failure surfaces as a confusing SIP-side error far from the real cause.
- **Blocking the worker.** If the async wiring is wrong and a module makes a *synchronous* Diameter call, one slow HSS response parks a SIP worker for the whole timeout. At registration storms this cascades fast. The whole point of the suspend/continue machinery is to avoid exactly this.

---

<p markdown="1" align="center">
  [← Table of contents](../) · [← 10.2 CSCF roles](32-ims-cscf.md) · [Next: 10.4 The full solution →](34-ims-full-solution.md)
</p>
