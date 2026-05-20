# 4. The script engine — pointer chapter

> [!IMPORTANT]
> This chapter is intentionally thin. The "script engine" — how `kamailio.cfg` becomes executable behaviour — is already covered from two directions: chapter 3.4 walks the routing engine from the *message-lifecycle* side, and chapter 5.2 walks it from the *KEMI-bridge* side. Rather than triple-cover the same machinery, this chapter is a brief map of what's where, plus a few internals that didn't fit in those chapters.

## What's where

| Topic | Covered in |
|---|---|
| What route blocks exist and when they fire | [3.4 The routing engine](10-routing-engine.md) |
| The cfg DSL's design constraints (no recursion, no collections) | [3.4](10-routing-engine.md) |
| How `kamailio.cfg` becomes an in-memory AST | [3.4](10-routing-engine.md), [2.4 Lifecycle](05-lifecycle.md) |
| Why cfg changes need a full restart | [2.4](05-lifecycle.md) |
| Module-function dispatch from cfg | [3.4](10-routing-engine.md), [5.2 KEMI bridge](13-kemi-bridge.md) |
| Pseudo-variables and lazy parsing | [3.2 The parsed message](08-parsed-message.md) |
| Lump-queuing as the side effect of script execution | [3.3 Lumps](09-lumps.md) |
| Sub-routes and how `route()` works | [3.4](10-routing-engine.md) |
| Per-route semantics of `exit` / `drop` / `return 0` | [3.4](10-routing-engine.md) |
| The cfg's bridge to KEMI scripts | [5.2 KEMI bridge](13-kemi-bridge.md) |

If you've read those chapters, you have the script engine. The rest of this chapter is the few details that didn't fit anywhere else.

## How a route block is actually structured in memory

After cfg parsing, each route block is an array of `cfg_action_t` structures. Each action is one of:

- A function call (`t_relay()`, `record_route()`, etc.) — holds the function pointer and a small argument list.
- A control-flow node (`if`, `else`, `switch`, `while`) — holds a child action list and a condition.
- An assignment (`$var(x) = ...`) — holds the target pseudo-variable handler and the expression.
- A jump (`return`, `exit`, `drop`, `break`) — handled directly by the executor.

The executor is a small interpreter (~few hundred lines) that walks this tree at runtime. It's not a virtual machine in the JIT sense — there's no bytecode, no compilation to native code. Just a direct AST walk with function-pointer dispatch.

This is why per-message script overhead is so low: there's no "compile-once-then-execute" indirection. The AST is already in the optimal form for the interpreter.

## How `exit`, `drop`, and `return 0` are signalled

All four script-level jump keywords — `exit`, `drop`, `return`, `break` — compile to a single opcode (`DROP_T`) in the executor. They differ only in which bit is OR-ed into the action context's `run_flags` field: `EXIT_R_F`, `DROP_R_F`, `RETURN_R_F`, `BREAK_R_F` respectively. `return 0` is auto-promoted to also set `EXIT_R_F`. The executor's main loop (`run_actions` in `src/core/action.c`) reads only `EXIT_R_F`/`RETURN_R_F`/`BREAK_R_F` to decide whether to keep walking the tree — `DROP_R_F` is never read by the executor.

What `DROP_R_F` is for: it's a signal **for the caller of `run_top_route`**. The routing engine — whichever piece of core or `tm` invoked the route block — gets back the `run_act_ctx` it passed in, inspects `ctx.run_flags & DROP_R_F`, and decides whether to skip its default continuation (forward the reply, send the branch, propagate the failure, etc.). This is why `drop` has different effects in different routes: each caller checks the bit at its own decision point. See [3.4](10-routing-engine.md) for the per-route table.

A corollary: routes called with `NULL` ctx — most notably `failure_route` and `event_route[tm:branch-failure]` — have no callable place to receive the bit. The script can still execute `drop`, but nobody reads the flag. Suppression in those routes happens through explicit side-effect calls (`t_reply()`, `t_drop_replies()`, `append_branch` + `t_relay()`) made before the script returns.

## Pseudo-variables as a dispatch table

Every `$xxx` in cfg is a registered pseudo-variable handler. The registration looks structurally identical to RPC and KEMI exports:

```c
static pv_export_t mod_pvs[] = {
    {{"hdr", sizeof("hdr")-1}, PVT_HDR, pv_get_hdr, NULL, pv_parse_hdr_name, NULL, 0, 0},
    {{"ru",  sizeof("ru")-1},  PVT_RURI, pv_get_ruri, pv_set_ruri, NULL, NULL, 0, 0},
    /* … */
};
```

Each entry: name, type tag, getter function, optional setter, optional name parser, etc. At parse time, the cfg parser looks up `$hdr` in the registered handlers and binds the script to the right function pointer. At runtime, evaluating `$hdr(X)` is a direct function call to `pv_get_hdr` with the parameter `X` — no name lookup.

This is why pseudo-variables are cheap and why some modules can add new ones (`$dlg_var`, `$shv`, `$avp`): the handler registration is open. The cfg DSL has no "type system" for variables; each `$xxx` is whatever the module that registered it says it is.

## The `if (function(...))` trick

A pattern that appears constantly in `kamailio.cfg`:

```kamailio
if (is_method("INVITE")) {
    record_route();
}

if (!t_relay()) {
    sl_send_reply("503", "Internal error");
}
```

What makes this work is that **module functions return a tri-state int** that the cfg interprets as truthy/falsy:

- Positive (typically `1`) → true, continue.
- Negative → false, condition false.
- Zero (rare) → drop the message entirely.

This is the "convention" baked into the C API. Module authors have to honour it for their function to be usable in `if (...)`. Almost every module function follows it.

The `!` operator inverts: `!t_relay()` is true when `t_relay()` returned non-positive. `&&` and `||` are normal short-circuit. Conditions can be combined with parentheses.

## Why the DSL doesn't grow

You might wonder why nobody has added loops over collections, real strings, or dictionaries to the cfg DSL. The reasons, in roughly the order Kamailio developers articulate them:

1. **It would invalidate the cheap-execution model.** A foreach over a dynamic collection requires per-iteration allocation, name resolution, garbage collection. The DSL is fast because none of these exist.
2. **KEMI already solves it.** Anything you'd want a "real language" for can be done in Lua/Python/JS/Ruby via KEMI. Adding it to cfg would duplicate KEMI without its benefits.
3. **Backwards-compatibility constraints.** The DSL has been roughly the same shape since 2001. Adding new syntactic categories would risk parser ambiguities with existing configs.

The result is a deliberate split: cfg DSL for the hot path with simple shape; KEMI for everything else. The boundary works precisely because it's enforced by the cfg DSL's intentional minimalism.

## When to actually read this chapter

If you've been working with Kamailio routes for a while and "why is my config doing X" is a debugging question, the answer is almost never in this chapter — it's in 3.4 or 5.2. This chapter is for the moment you ask "*how* does the script actually work," not "what should my script do."

---

<p markdown="1" align="center">
  [← Table of contents](../) · [← 9.2 Term map](28-term-map.md)
</p>
