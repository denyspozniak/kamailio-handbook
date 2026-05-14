# 9.2 Term map

Quick glossary of Kamailio-specific terms used throughout the handbook. SIP-protocol terms (UAC, UAS, INVITE, etc.) are taken as known from RFC 3261.

| Term | Means |
|---|---|
| **AOR** | Address Of Record — the SIP identity (`alice@example.com`) under which contacts are registered. |
| **AVP** | Attribute-Value Pair — a script-accessible named variable, scope-bound to a transaction or branch. Survives async suspend/resume. |
| **branch** | One destination within a forked transaction. Each branch has its own outgoing buffer, lump set, retransmission state. |
| **BINRPC** | Binary RPC protocol over Unix socket. The default transport for `kamcmd`. |
| **cell** | A `tm` transaction record in shm. Holds branches, timers, refcount, hooks. |
| **cfg DSL** | The configuration language: `kamailio.cfg`. Pre-compiled to an AST at startup, executed per message. |
| **child_init()** | Module hook that runs once per worker after fork. Where per-process resources (interpreter state, DB connections) get set up. |
| **contact** | A SIP `Contact` URI, a binding from an AOR to a specific endpoint. |
| **dialog** | A call-level state record spanning multiple transactions. Maintained by the `dialog` module. |
| **dispatcher set** | A named, numbered group of destinations with a selection algorithm and probing config. |
| **dmq** | Distributed Message Queue. The peer-to-peer replication mesh across multiple Kamailio instances. |
| **FFI** | Foreign Function Interface — the C-to-script bridge used by KEMI to dispatch into Lua/Python/JS/Ruby interpreters. |
| **htable** | Generic shm hash table, the "poor man's Redis." |
| **KEMI** | Kamailio Embedded Interface. The mechanism for writing routing logic in Lua, Python, JS, or Ruby. |
| **`KSR.*`** | The global namespace exposed in KEMI scripts. `KSR.tm.t_relay()` calls the registered C function. |
| **lump** | A queued message mutation (add or delete bytes at an offset). Applied in one pass at send time. |
| **mod_init()** | Module hook that runs once in the main process, before fork. Where shm is allocated and RPC commands are registered. |
| **pkg** | Per-worker private memory heap. Lifetime is one message; not visible to other workers. |
| **pseudo-variable** | A script-side getter/setter on the `sip_msg` or runtime state. Names start with `$` — `$ru`, `$tu`, `$hdr(X)`, `$var(x)`, `$shv(x)`. |
| **rank** | Integer ID of a forked worker process. Used for RNG seeding, timer-slot selection, log disambiguation. |
| **RPC** | Remote Procedure Call. Kamailio's runtime introspection/control API. Exposed via BINRPC and JSON-RPC. |
| **`sip_msg`** | The C struct holding a parsed message: original buffer, header list, body, lump lists, flags. Lives in pkg, one per worker per message. |
| **shm** | Shared memory — one `mmap()`'d region accessible from every worker. Lifetime spans messages and workers. |
| **`$shv`** | Shared variable. A named global in shm. |
| **`$sht`** | htable accessor. `$sht(table=>key)` reads/writes an entry. |
| **t_continue()** | Resume a previously-suspended transaction with a result. |
| **t_relay()** | Forward a request statefully via `tm`. Creates the transaction. |
| **t_suspend()** | Pause the current transaction's progress, release the worker, allow asynchronous resume later. |
| **tm** | Transaction Module. Tracks SIP transactions in shm, manages retransmission and forking. |
| **topos** | Topology hiding module. Rewrites messages so the proxy is invisible to endpoints. |
| **transaction** | A SIP request plus all its responses, including retransmissions. The unit of state in `tm`. |
| **usrloc** | User Location module. The registrar's contact cache, backed optionally by DB. |
| **WAIT timer** | Per-transaction timer that lingers after a final response, absorbing retransmissions before cleaning up. |
| **wheel (timer)** | Time-bucketed array used by tm's timer process. O(1) to schedule, O(K) per tick where K is expirations. |

## Notation conventions used in code samples

- `something()` — module function callable from cfg.
- `$xx` or `$xx(arg)` — pseudo-variable, evaluated against the current `sip_msg`.
- `kamcmd <method>` — BINRPC command invoked from the host shell.
- `event_route[<name>]` — a runtime hook, dispatched by the runtime, not by an inbound message.
- `KSR.<module>.<function>` — KEMI-side call into a registered C function.

## Where each concept is covered

| If you're confused about… | See |
|---|---|
| Why there are so many processes | Chapter 2.1 |
| Why `$var` doesn't survive across messages | Chapter 2.1, 2.2 |
| Why `remove_hf` doesn't immediately remove the header | Chapter 3.3 |
| Why `kamailio.cfg` can't be reloaded | Chapter 2.4 |
| Why Lua globals aren't shared between workers | Chapter 5.3 |
| Why `dispatcher.reload` mid-call can shift stickiness | Chapter 8.4 |
| Why dmq is "eventually consistent" | Chapter 8.5 |
| Why `kamcmd` is short but capable | Chapter 7.2 |

This concludes the handbook. The next time something in production looks strange, the path is: check `kamcmd` (chapter 7.2), read the relevant chapter on what's involved, and if needed, drop into the asipto devel-guide for the implementation details that this handbook deliberately summarised.

---

<p markdown="1" align="center">
  [← Table of contents](../) · [← 9.1 Process roles](27-process-roles.md) · [Next: 9.3 What's new →](30-whats-new.md)
</p>
