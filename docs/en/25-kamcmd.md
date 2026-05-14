# 7.2 `kamcmd` — the operator's lever

> [!IMPORTANT]
> `kamcmd` is a thin BINRPC client over a Unix socket — it doesn't *know* anything special about Kamailio. The capability comes entirely from the commands registered in the running Kamailio instance. But because every important runtime knob and every observability hook is wired through that registry, `kamcmd` is in practice **the** tool for operating a Kamailio server.

## What it actually is

`kamcmd` is ~1 000 lines of C. It opens a Unix socket, serialises a method-and-arguments pair to BINRPC, reads back a BINRPC response, and pretty-prints it. That's the entire program. The intelligence — the list of available commands, what arguments they take, what state they expose — lives on the other side of the socket, registered into Kamailio's RPC registry by every loaded module.

Typical invocation:

```bash
kamcmd <method> [arg1] [arg2] …
```

The connection target defaults to `/var/run/kamailio/kamailio_ctl` (or `/run/kamailio/kamailio_ctl`). `-s <path>` overrides. There's no auth, no config — just the socket path.

## The five commands you'll run constantly

If you operate Kamailio for any length of time, these will be in your shell history dozens of times:

```bash
# 1. Is the heap healthy?
kamcmd core.shmmem
kamcmd core.pkgmem all

# 2. How many transactions / dialogs / contacts right now?
kamcmd tm.stats
kamcmd dialog.stats_active
kamcmd ul.stats

# 3. What's in this table, exactly?
kamcmd htable.dump my_auth_cache
kamcmd dispatcher.list
kamcmd ul.dump

# 4. What's going on across the cluster?
kamcmd dmq.list_nodes

# 5. Toggle log level live (without restart)
kamcmd dbg.set_level 3                  # turn debug on
kamcmd dbg.set_level 2                  # back to info
```

These five together answer the bulk of "is Kamailio okay right now?" investigations. Memory, in-flight counts, table contents, cluster state, log noise. Everything else is variations.

## The hidden gem: `rpc.entries` and `system.listMethods`

When you don't remember a command name (and you won't, because there are hundreds), the runtime tells you:

```bash
kamcmd system.listMethods           # full list of currently-loaded RPC methods
kamcmd rpc.entries                  # same, with one-line descriptions
kamcmd <prefix>.help                # module-specific help where supported
```

`system.listMethods` is the authoritative answer to "what can I call on this Kamailio?" because it reflects the actual loaded module set, not just docs. A module that isn't loaded doesn't expose its commands here.

## Reading the output

Most commands return a structured value — a map, an array, a nested structure. `kamcmd` renders them as indented text. For example, `tm.stats`:

```
{
  current: 0
  total: 18234
  current_size: 0
  rpl_received: 18229
  rpl_generated: 5
  rpl_sent: 18234
  6xx: 0
  5xx: 0
  4xx: 0
  3xx: 0
  2xx: 18229
  …
}
```

For machine consumption, `kamcmd -f '%v'` formats single values, useful for shell scripting:

```bash
free_shm=$(kamcmd -f '%v' core.shmmem | grep ^free | awk '{print $2}')
```

For richer structured output, prefer JSON-RPC over the HTTP endpoint — `kamcmd`'s output format is human-first.

## Manipulating state, carefully

A lot of commands are read-only — `stats`, `dump`, `list`. But some are mutators. The mutator ones tend to follow naming patterns:

```bash
# set / delete table entries
kamcmd htable.sets my_cache key123 "value"
kamcmd htable.delete my_cache key123

# mark a dispatcher destination down (or back up)
kamcmd dispatcher.set_state ai 1 "sip:gw1:5060"   # ai = active inactive

# kick a dialog out of the cache
kamcmd dlg.terminate_dlg <call-id> <from-tag>

# reload a module's in-memory tables from DB
kamcmd dispatcher.reload
kamcmd permissions.addressReload
kamcmd htable.reload my_cache
```

> [!WARNING]
> Mutators are not idempotent or transactional. `htable.sets` with a stale value overwrites; `dispatcher.set_state` flips the in-shm flag immediately without confirmation. The Unix-socket access model assumes the caller knows what they're doing.

## What `kamcmd` can't do

A few things end up surprising people:

- **It can't tail logs.** Logs go to syslog or stdout depending on cfg; RPC isn't a log channel. Use `journalctl -fu kamailio` or whatever your log destination is.
- **It can't capture SIP traffic.** That's tcpdump/sngrep territory. RPC sees Kamailio's internal state, not the wire.
- **It can't change `kamailio.cfg` semantics.** Routing logic is baked into the AST at startup (chapter 2.4). RPC can only flip whatever module parameters were declared mutable.
- **It can't talk to a Kamailio that isn't running.** The socket only exists while the main process is up. After a crash, `kamcmd` reports "connection refused" — by design.

## Why this design is good

`kamcmd` is a minimal client because Kamailio's RPC layer is the actual product. Move a command to a different module, change the format of its output, add a new command — all transparent to `kamcmd`. The tool was written once a decade ago and rarely needs changes. Everything interesting happens in module code, exposed through `rpc_export` tables.

This is the architecture that makes operations sustainable: there's no second codebase to keep in sync, no "kamcmd doesn't support that new feature yet," no "let me update the docs separately." Whatever the running server can do, you can call.

The next chapter looks at the other half of the operator's surface area: event routes, which let cfg react to runtime events the same way it reacts to incoming messages.

---

<p markdown="1" align="center">
  [← Table of contents](../) · [← 7.1 RPC architecture](24-rpc-architecture.md) · [Next: 7.3 Event routes →](26-event-routes.md)
</p>
