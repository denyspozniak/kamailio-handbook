<h1 align="center">Kamailio Handbook — English</h1>

<p align="center">
  <em>How Kamailio is built on the inside.</em>
</p>

<p align="center">
  <img alt="Kamailio" src="https://img.shields.io/badge/Kamailio-5.8.x-1f6feb?style=flat-square">
  <img alt="Lang" src="https://img.shields.io/badge/lang-English-1f6feb?style=flat-square">
  <a href="../uk/README.md"><img alt="Switch to Ukrainian" src="https://img.shields.io/badge/switch_to-Українська-bf8700?style=flat-square"></a>
</p>

---

> [!IMPORTANT]
> This handbook is **deliberately not a re-telling of the official docs**. It assumes you already know what Kamailio is at a surface level and instead drills into the runtime, the message lifecycle, the script engine, KEMI, and the architectural tricks that make Kamailio behave the way it does. There is no module-by-module reference here.

**Sources used:**
- [asipto/kamailio-devel-guide](https://github.com/asipto/kamailio-devel-guide) — internals reference by the original maintainer; goes deep on data lumps, parser, memory, locking, RPC.
- [kamailio.org/wikidocs](https://www.kamailio.org/wikidocs/) — for background and the surface-level API.
- [github.com/kamailio/kamailio](https://github.com/kamailio/kamailio) — actual implementation in C, the final source of truth.

## How a SIP request flows through Kamailio

```mermaid
flowchart LR
    In([SIP IN]) --> Parser[Parser]
    Parser --> Sanity[Sanity checks]
    Sanity --> RR[request_route]
    RR --> Mods[[Module functions<br/>tm · rr · auth · dispatcher · …]]
    Mods --> Decision{Stateful?}
    Decision -- yes --> TM[tm: create transaction]
    Decision -- no --> SL[sl: stateless forward]
    TM --> Out([SIP OUT])
    SL --> Out

    classDef io fill:#238636,stroke:#238636,color:#fff
    classDef core fill:#1f6feb,stroke:#1f6feb,color:#fff
    classDef mod fill:#bf8700,stroke:#bf8700,color:#fff
    classDef branch fill:#6e7681,stroke:#6e7681,color:#fff

    class In,Out io
    class Parser,Sanity,RR core
    class Mods,TM,SL mod
    class Decision branch
```

A single received SIP message walks through this pipeline. Most of what looks like "magic" in a Kamailio config is just deciding which way it branches — and the handbook unpacks every box above.

## Table of contents

### 1. Preface
- [1.1 Introduction](01-introduction.md) — signalling vs media, mental model, what to expect ✅

### 2. The Runtime
- [2.1 Process model](02-process-model.md) — main, attendant, timer, workers — what each one is for ✅
- [2.2 Memory architecture](03-memory-architecture.md) — `pkg` vs `shm`, the custom allocator, lifetime rules ✅
- [2.3 Concurrency primitives](04-concurrency.md) — locks, atomic ops, per-bucket sharding ✅
- [2.4 Lifecycle](05-lifecycle.md) — startup, config reload, graceful shutdown ✅
- [2.5 Sizing & tuning](06-sizing-and-tuning.md) — workers, memory, kernel knobs per traffic pattern (proxy / registrar / stateful / WS) ✅

### 3. SIP Message Lifecycle
- [3.1 Reception](07-reception.md) — sockets, listeners, how transport demultiplexes ✅
- [3.2 The parsed message](08-parsed-message.md) — `sip_msg` struct, **lazy** header parsing, the cost model ✅
- [3.3 Lumps](09-lumps.md) — how mutations are *queued* rather than applied (this is the speed trick) ✅
- [3.4 The routing engine](10-routing-engine.md) — `request_route`, `branch_route`, `failure_route`, `onreply_route`, `event_route` ✅
- [3.5 Forwarding and replies](11-forwarding.md) — assembling the outgoing message from buffer + lumps ✅

### 4. The Script Engine
- 4.1 The cfg DSL — why a custom language, what it optimises for
- 4.2 Parsing, AST, execution — from `kamailio.cfg` to per-message bytecode
- 4.3 Module-function dispatch — the C↔script FFI
- 4.4 Pseudo-variables as an indirection layer — how `$var(x)`, `$avp(y)`, `$hdr(z)` actually work

### 5. KEMI — embedded scripting
- [5.1 What problem KEMI solves](12-kemi-overview.md) — when the cfg DSL stops being enough ✅
- [5.2 The bridge](13-kemi-bridge.md) — embedding Lua, Python, JS, Ruby into the C runtime ✅
- [5.3 Lifecycle](14-kemi-lifecycle.md) — per-worker interpreter, what survives between messages, reload ✅
- [5.4 Tradeoffs](15-kemi-tradeoffs.md) — when KEMI wins, when native cfg wins, the hybrid pattern ✅

### 6. State, Transactions, Dialogs
- [6.1 Transactions (`tm`)](16-tm-internals.md) — hash tables in shm, timer wheels, retransmission ✅
- [6.2 Dialogs](17-dialogs.md) — how `dialog` augments `tm` to track full calls ✅
- [6.3 The `usrloc` pattern](18-usrloc.md) — in-memory cache, DB sync, generalised ✅

### 7. Control Plane
- [7.1 RPC architecture](24-rpc-architecture.md) — BINRPC vs JSON-RPC, the command registry, auth posture ✅
- [7.2 `kamcmd`](25-kamcmd.md) — the operator's lever, the five commands you'll run constantly ✅
- [7.3 Event routes](26-event-routes.md) — programmable hooks into runtime lifecycle ✅

### 8. Cool architectural tricks
- [8.1 Topology hiding (`topos`)](19-topos.md) — rewriting calls so the topology vanishes ✅
- [8.2 Async transactions](20-async-transactions.md) — `t_suspend` / `t_continue` for non-blocking flows ✅
- [8.3 `htable`](21-htable.md) — shared-memory hash tables as a poor man's Redis ✅
- [8.4 `dispatcher`](22-dispatcher.md) — hash-based stickiness, gateway sets, failover algorithms ✅
- [8.5 `dmq`](23-dmq.md) — distributed state sync between Kamailio instances ✅

### 9. Reference
- 9.1 Process roles glossary
- 9.2 Term map

---

<p align="center">
  <a href="../uk/">🇺🇦 Українська</a>
</p>
