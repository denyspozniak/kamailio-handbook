# 9.1 Process roles glossary

A quick reference for what each process in a running Kamailio actually is, in the order you'd see them from `ps -ef | grep kamailio`.

| Process | Multiplicity | Role | Touches SIP? | Detail |
|---|---|---|---|---|
| **main** | 1 | Parent of every other process. Reaps dead children, propagates signals. | No | Spawned when `kamailio` starts; PID == the one in `/var/run/kamailio.pid`. |
| **attendant** | 1 | Secondary supervisor handling a subset of lifecycle signals. | No | Legacy from SER lineage. Mostly ignorable. |
| **udp receiver** | `children` per UDP listener (default 8) | Bulk SIP traffic handlers. Each loops on `recvfrom()`. | Yes | Where `request_route` runs for UDP traffic. One worker per packet, start to finish. |
| **tcp main** | 1 | `accept()`s new TCP/TLS connections, dispatches FDs to TCP workers. | No (signalling-plane only) | Splits accept-from-message-processing. |
| **tcp worker** | `tcp_children` (default 4) | Reads SIP streams from owned TCP connections, frames messages, calls `receive_msg()`. | Yes | Where `request_route` runs for TCP, TLS, WebSocket traffic. |
| **timer** | 1 | Fires fast (~100 ms tick) timers: tm retransmissions, dialog keepalive, dispatcher probing. | Yes (it can emit SIP) | Drives the timer wheels described in chapter 6.1. |
| **slow timer** | 1 | Fires slow timers: wait timer in tm, cleanup tasks. | No | Separated from fast timer so housekeeping doesn't starve retransmissions. |
| **ctl** | 1 | Listens on the BINRPC Unix socket. | No | What `kamcmd` talks to. |
| **jsonrpcs** | 1 (when loaded) | Listens for JSON-RPC over HTTP/FIFO/UDP. | No (control plane) | The HTTP-based RPC server. |
| **dialog (keepalive)** | 1 (when loaded with KA) | Sends OPTIONS probes to confirmed dialogs. | Yes | Detects partition-induced dead calls. |
| **htable (expiry)** | 1 (when loaded) | Sweeps expired htable entries periodically. | No | One sweep across all htable instances. |
| **dispatcher (probing)** | 1 (when loaded with probing) | Pings dispatcher destinations with OPTIONS, marks dead/alive. | Yes | Liveness detector for gateways. |
| **dmq (worker)** | 1+ (when loaded) | Handles incoming DMQ messages from peer instances. | No | The replication transport. |
| **usrloc (expiry)** | 1 (when loaded) | Sweeps expired contacts; flushes dirty entries to DB. | No | The usrloc pattern from chapter 6.3. |
| **app_lua / app_python helpers** | varies | Per-language reload coordinators, if the language module has them. | No | Each worker has its own interpreter; these helpers do bookkeeping. |
| **xhttp_prom / xhttp_pi / …** | 1 each | HTTP-based management interfaces, when loaded. | No | Each opens its own listener inside Kamailio. |

The number of processes you'll actually see depends on which modules are loaded. A minimal config with just `tm` and `sl` runs maybe a dozen processes. A production deployment with dialog, dispatcher, dmq, usrloc, htable, KEMI, multiple HTTP interfaces — easily 25–40.

## How to identify them from outside

The processes set their own names via `prctl(PR_SET_NAME)`, so `ps` shows readable descriptors:

```
kamailio: main process
kamailio: udp receiver child=3 udp:10.0.0.1:5060
kamailio: tcp main process
kamailio: tcp receiver (1) child=2
kamailio: timer
kamailio: slow timer
kamailio: ctl handler
kamailio: jsonrpcs http handler
kamailio: Dialog KA Timer
kamailio: HTable Expire Timer
kamailio: Dispatcher Probing
kamailio: DMQ Worker [0]
…
```

The format is `kamailio: <role> [<index>]` for indexed workers. The `rank` mentioned in chapter 2.1 is the same index, used internally for RNG seeding and timer slot selection.

## What gets restarted on a worker crash

| Process kind | If it dies… |
|---|---|
| UDP/TCP/timer workers | Main re-forks immediately |
| TCP main | Main re-forks; existing TCP connections are lost |
| Module helpers (dialog KA, htable expire, dispatcher probe, dmq, etc.) | **Usually not restarted.** Module-specific behaviour. |
| ctl / jsonrpcs | Main re-forks |
| Main itself | Whole Kamailio terminates |

> [!WARNING]
> A module-helper that dies and doesn't get restarted (e.g. dispatcher probing) silently degrades the service — gateways stop being probed, dead destinations aren't marked, calls go to nowhere. Alert on `SIGCHLD` rate, not just liveness of the main process.

---

<p align="center">
  <a href="./">← Table of contents</a> · <a href="26-event-routes.md">← 7.3 Event routes</a> · <a href="28-term-map.md">Next: 9.2 Term map →</a>
</p>
