# 7.3 Event routes — runtime hooks

> [!IMPORTANT]
> Most route blocks in Kamailio fire because a SIP message arrived (`request_route`, `onreply_route`) or because `tm` decided something about a transaction (`branch_route`, `failure_route`). **Event routes** fire because of *something else* — a worker started, a peer went down, an HTTP request hit Kamailio's listener, a timer expired, a script reload happened. They are the programmable hook surface for the runtime itself.

## How they look

An event route is just a named route block, declared with a module-and-event prefix:

```kamailio
event_route[tm:branch-failure] {
    xlog("L_INFO", "branch failed for $T(reply_code) $T(reply_reason)\n");
}

event_route[dispatcher:dst-down] {
    xlog("L_WARN", "gateway $rd just went DOWN\n");
}

event_route[htable:expired:auth_cache] {
    xlog("L_DBG", "auth cache entry expired: $shtex(key)\n");
}
```

When the runtime detects one of these events, it dispatches the named route exactly like `request_route` — pre-compiled AST, same module-function call surface, same pseudo-variables (modulo what's contextually available). The difference is what triggers it.

## The categories of events

Different modules expose different events. The well-known ones:

| Event | When it fires | What's available |
|---|---|---|
| `event_route[tm:branch-failure]` | A specific branch got a non-2xx final | `$T(...)` for transaction info |
| `event_route[tm:local-response]` | tm built a reply (timeout, etc.) | The reply being constructed |
| `event_route[xhttp:request]` | An HTTP request hit a Kamailio socket | `$hu`, `$rb` for URL and body |
| `event_route[xhttp_pi:request]` | Same, but for the management interface | — |
| `event_route[dispatcher:dst-down]` | A destination was just marked dead | `$rd` for destination URI |
| `event_route[dispatcher:dst-up]` | A destination came back | `$rd` |
| `event_route[htable:expired:<table>]` | An entry just expired and was removed | `$shtex(key)`, `$shtex(value)` |
| `event_route[htable:mod-init]` | Table initialised at startup | — |
| `event_route[dialog:start]` | A dialog moved from EARLY to CONFIRMED | `$dlg_var(...)` |
| `event_route[dialog:end]` | A dialog terminated | `$dlg_var(...)` |
| `event_route[dmq:peer-down]` | A dmq peer stopped responding | Peer URI |
| `event_route[sip:reply-lost]` | A reply could not be sent back | — |
| `event_route[core:worker-pre-init]` | Just before workers start (in main) | — |

The naming convention is consistent: `module:event-name` or `module:event-name:specific-arg`. The module documentation lists what events it raises.

## Why they exist

Three reasons, in increasing order of usefulness:

**1. Side effects without polluting `request_route`.** A handler that needs to fire on dispatcher state changes — to update a Prometheus counter, push to a webhook, log to a custom file — doesn't belong inside `request_route`. It belongs in an event route that fires only when the event actually happens.

**2. State machines.** Combining `event_route[dialog:start]` and `event_route[dialog:end]` gives you a place to maintain custom per-call counters and timers that aren't worth implementing as a new module.

**3. Async chaining.** The async chapter (8.2) showed `t_continue()` driving execution into a resume-route. That resume-route is, mechanically, an event route — same dispatch, same context model. Any time you do an external call and want to come back, the destination is an event route.

## What's different about the execution context

Event routes run **outside the context of an incoming SIP message** (mostly). Some pseudo-variables that work in `request_route` are NULL or undefined in an event route — `$ru`, `$tu`, `$si` may have no meaning if the event isn't tied to a message. Read the module's documentation for which fields are populated for which events.

What you can always do:
- Call most module functions (subject to context — `t_relay()` doesn't work without a transaction).
- Log via `xlog`.
- Touch htables and other shared state.
- Issue RPC events back into the system (e.g. notify dmq peers).
- Read and write `$shv()` and `$shtex()`.

What you usually can't do:
- Call `t_relay()` — there's no original message to relay.
- Modify lumps — there's no `sip_msg` to attach them to.
- Use `$var(...)` reliably — the worker's per-message arena may be empty.

> [!TIP]
> Event routes are short by design. If your handler is more than 30 lines, the logic probably belongs in a script (KEMI) or a module — not in cfg. Event routes work best as **dispatch glue**: detect, log, increment a counter, call a sub-route or a script function.

## Where event routes plug into the rest

Two of the architectural pieces we've already covered explicitly use event routes:

- **Async transactions** (chapter 8.2) — `t_continue()` enters an event-route-shaped resume.
- **KEMI** (chapter 5.2) — `event_route_callback("event:name", "ksr_handler")` lets you direct an event route's dispatch into a script function instead of a cfg block. Useful when the event-handling logic is complex enough to want a real language.

The fact that all of these share the same machinery is intentional: there's only one event-dispatch mechanism in Kamailio, and it's reused everywhere something needs to fire outside of normal SIP processing.

## A small worked example

A common operational pattern: when a dispatcher destination goes down, log to a custom dashboard and notify dmq peers so they all mark the same destination down.

```kamailio
event_route[dispatcher:dst-down] {
    xlog("L_ALERT", "DISPATCHER_DOWN $rd\n");
    
    # post to internal dashboard via HTTP
    $var(body) = "{\"event\":\"dst-down\",\"dst\":\"$rd\"}";
    http_async_query("http://dashboard.internal/sip-events", "dashboard_done");
    
    # let other Kamailio nodes know
    $sht(degraded=>$rd) = 1;
    # dmq replicates the htable change
}

event_route[dashboard_done] {
    if ($http_rs != 200) {
        xlog("L_WARN", "dashboard rejected event: $http_rs\n");
    }
}
```

Three event routes wired together: the actual `dispatcher:dst-down`, a `dashboard_done` resume for the async HTTP call, and (implicitly) the dmq replication of the htable change which fires its own handlers on the peer nodes.

The next chapter wraps the handbook with a short reference: the process role glossary and a term map you can scan back to when something doesn't make sense.

---

<p markdown="1" align="center">
  [← Table of contents](../) · [← 7.2 kamcmd](25-kamcmd.md) · [Next: 9.1 Process roles →](27-process-roles.md)
</p>
