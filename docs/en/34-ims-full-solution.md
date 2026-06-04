# 10.4 What you still need around Kamailio

> [!IMPORTANT]
> **Kamailio is the CSCF signalling plane, and nothing else.** It registers users, routes SIP, and queries Diameter peers. It does not store subscribers, decide policy, rate calls, or touch RTP. A working IMS is Kamailio plus the surrounding systems below.

## Scope

| Kamailio (CSCF) does | Kamailio does **not** do |
|---|---|
| SIP registration & routing (P/I/S-CSCF) | Store the subscriber database |
| Authentication challenge (using HSS vectors) | Generate the auth vectors |
| Trigger services via iFC/ISC | Be the application server |
| Ask for QoS/media policy (Rx) | Decide or enforce policy |
| Ask for charging (Ro/Rf) | Rate or bill the call |
| — | Relay or transcode media (RTP) |

Everything in the right-hand column is a separate system.

## The surrounding components

```mermaid
flowchart TB
    subgraph SIG["Signalling — Kamailio"]
        P[P-CSCF]
        I[I-CSCF]
        S[S-CSCF]
    end
    subgraph SUB["Subscriber & policy"]
        HSS[(HSS)]
        PCRF[(PCRF / PCF)]
        OCS[(OCS / CHF)]
        DRA{{DRA / SLF}}
    end
    subgraph MEDIA["Media & access"]
        RTP[rtpengine]
        CORE[EPC / 5GC<br/>SMF · UPF]
        DNS[DNS<br/>ENUM/NAPTR/SRV]
        DB[(DB<br/>MariaDB / Valkey)]
    end

    P --- I --- S
    I -.Cx.-> DRA -.-> HSS
    S -.Cx.-> DRA
    P -.Rx.-> PCRF
    S -.Ro/Rf.-> OCS
    S --- DB
    P --- RTP
    CORE --- P
    P --- DNS

    classDef cscf fill:#1f6feb,stroke:#1f6feb,color:#fff
    classDef sub fill:#bf8700,stroke:#bf8700,color:#fff
    classDef media fill:#238636,stroke:#238636,color:#fff
    class P,I,S cscf
    class HSS,PCRF,OCS,DRA sub
    class RTP,CORE,DNS,DB media
```

**HSS — Home Subscriber Server.** The subscriber database and the auth-vector generator. Kamailio talks to it over Cx. Open-source choice that works: **open5gs** (its HSS function).

**PCRF / PCF — Policy.** Decides whether a media flow is allowed and what QoS it gets, and tells the core to set up a dedicated bearer. P-CSCF talks to it over Rx. open5gs again.

**OCS / CHF — Charging.** Online charging (prepaid balance, credit reservation) and offline (CDR generation). S-CSCF talks to it over Ro/Rf. Open-source choice: **CGRateS**, a capable real-time rating engine with a Diameter agent.

**DRA / SLF — Diameter routing.** In anything beyond a single-HSS lab you put a **Diameter Routing Agent** between the CSCFs and the HSS/PCRF/OCS, so the CSCF has one Diameter peer to point at instead of N. Open-source choice: **freeDiameter** as a relay/DRA.

**rtpengine — media.** Relays (and optionally transcodes/encrypts) RTP, and handles ICE/SRTP for WebRTC access. Kamailio steers it via the `rtpengine` module but never carries media itself.

**DNS.** IMS routing leans hard on DNS: **NAPTR/SRV** to find CSCFs, **ENUM** to turn `tel:` numbers into SIP URIs. A misconfigured resolver breaks call routing in ways that look like CSCF bugs. **CoreDNS** is a clean choice (and it's already the default in Kubernetes).

**DB.** S-CSCF registration state needs persistence to survive restarts. **MariaDB/MySQL** is the tested path for `ims_usrloc_scscf` (hardcoded SQL — see [10.2](32-ims-cscf.md)); **Valkey/Redis** is lighter and is what rtpengine wants for HA, but needs schema handling on the Kamailio side.

**EPC / 5GC core.** The device needs an IP bearer and a route to the P-CSCF before any of the above applies. That's the packet core — **SMF/UPF** in 5G, PGW in 4G — which also discovers the P-CSCF address and (with the PCRF) sets up the dedicated voice bearer. open5gs covers this too.

**Monitoring.** Diameter and SIP both fail quietly; you want **Prometheus/Grafana** for metrics and **Loki**-style log aggregation from day one, plus packet capture (`sip || diameter || gtpv2`) for the inevitable flow debugging.

## A minimal complete stack

> **Kamailio** (P/I/S-CSCF) + **open5gs** (HSS, PCRF, SMF, UPF) + **CGRateS** (OCS) + **freeDiameter** (DRA) + **rtpengine** (media) + **CoreDNS** + a **DB** + **Prometheus/Grafana/Loki** + a **test UE**.

This is the component list assembled in the lab in [10.5](35-ims-lab.md).

---

<p markdown="1" align="center">
  [← Table of contents](../) · [← 10.3 The Diameter side](33-ims-diameter.md) · [Next: 10.5 A software IMS lab →](35-ims-lab.md)
</p>
