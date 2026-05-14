# 3.2 The parsed message

> [!IMPORTANT]
> Kamailio **does not fully parse a SIP message on arrival**. It does the minimum needed to know the message is well-formed and what kind of message it is. Headers, URIs, bodies are parsed *on first access*. This is the single biggest reason routes that touch only a few headers run as fast as they do.

## `struct sip_msg`

Every received SIP message lives in a `struct sip_msg` allocated in the worker's pkg heap (see [chapter 2.2](03-memory-architecture.md)). It's the central data structure of message processing — every module function takes it as the first argument, every pseudo-variable is ultimately a getter on its fields, every lump hangs off it.

What's in it, schematically:

```
struct sip_msg {
    char       *buf;          // pointer at the original received bytes
    unsigned    len;          // length of buf
    msg_type    type;         // request or reply
    method_id   first_line;   // method + URI (request) or status + reason (reply)
    hdr_field  *headers;      // linked list of parsed headers
    hdr_field  *callid;       // shortcut → the Call-ID header (NULL until parsed)
    hdr_field  *to;           // shortcut → the To header (NULL until parsed)
    hdr_field  *from;         // shortcut → the From header
    hdr_field  *cseq;
    hdr_field  *contact;
    /* …a dozen more shortcuts… */
    str         body;         // pointer + length into buf; body parsing is separate
    lump       *add_rm;       // lumps for forwarded message (next chapter)
    lump_rpl   *reply_lump;   // lumps for the reply
    /* …flags, dst_addr, send_socket, force_send_socket, … */
};
```

The struct itself is small. The bytes it points into — `buf` — are the original received message, untouched. Nothing in the runtime ever copies the buffer; everything is offsets and pointers into the same bytes.

> [!TIP]
> When you write `$ru` (request URI), `$tu` (To URI), `$hdr(X-Foo)` in a routing script, you're triggering Kamailio to **parse on first access** if it hasn't already. The pseudo-variable getter calls `parse_uri()`, `parse_to()`, or `parse_headers(msg, HDR_X_F)` under the hood, the result is cached on the `sip_msg`, and subsequent accesses are free.

## The first-pass parse

When `receive_msg()` runs (see [chapter 3.1](07-reception.md)), it calls `parse_msg()` which does only this:

1. Find the **first line** — the request line (`METHOD URI SIP/2.0`) or status line (`SIP/2.0 STATUS REASON`). Confirm it parses.
2. Walk the header section, registering each header's **name and byte range** in a linked list. **Header values are not parsed.** The parser knows where `To:` starts and ends, but not who's in it.
3. Identify the body offset and length, if `Content-Length` is present.

That's it. After `parse_msg()` returns, you know it's an `INVITE` going to `sip:bob@example.com`, but if you ask "what's the `To` URI?" you'll get NULL until something explicitly parses it.

This isn't laziness — it's load-bearing. A typical request_route might be 30 lines of script that touches `$ru`, `$tu`, maybe `$hdr(Authorization)`, and forwards. Fully parsing every header on every message — `Via`, `Record-Route`, `Contact`, `Allow`, `Supported`, `User-Agent`, dozens more — would cost an order of magnitude more CPU per message for no benefit.

## Parsing on demand

When the script (or a module function) needs a specific header, it calls one of the parser entry points:

```c
parse_headers(msg, HDR_TO_F, 0);    // parse up to and including To
parse_to(msg);                       // parse the To header's value into addr_body
parse_uri(uri.s, uri.len, &parsed); // parse a URI string into struct sip_uri
parse_body(msg);                     // parse SDP or other body
```

`parse_headers()` takes a **bitmask** of which headers you want. It walks the header list, parsing values for any header that matches a bit in the mask, until it has parsed everything requested. The work is cumulative: parsing `HDR_TO_F | HDR_FROM_F` after already parsing `HDR_TO_F` only does the From work.

The result of each parse is cached on the `sip_msg`. The shortcut pointer (`msg->to`, `msg->from`) is set, the header's `parsed` field on the `hdr_field` struct holds the structured value (`to_body`, `from_body`, etc.), and subsequent accesses return immediately.

## What "parsed" actually looks like

A `hdr_field` after parsing holds two things:

- The original bytes — `name.s`/`name.len` for the header name, `body.s`/`body.len` for the value, both as `str` pointers into the message buffer.
- The structured `parsed` pointer, downcast based on header type — `to_body*` for `To`, `via_body*` for `Via`, etc.

The structured form contains pre-extracted fields. For `To`: display name, URI, tag, parameters. For `Via`: protocol, host, port, branch parameter, received parameter, more. These fields too are pointers into the original buffer, not copies — the `tag` of a `To` header is just a `(ptr, len)` pair into the bytes that arrived from the network.

Bodies follow the same pattern. `parse_body()` recognises content types (`application/sdp` most commonly), parses the body into a structured tree (for SDP: `sdp_info` with sessions, streams, media descriptions), and caches it. Modules that touch the body (rtpengine, sdpops, presence) trigger this parse.

## Why nothing is copied

The architectural choice that ties all of this together: **the original buffer is never copied or modified during processing.** Every parsed structure points back at byte ranges in `msg->buf`. The headers' `body.s` is a pointer into `buf`. The `To`'s `uri.s` is a pointer into `buf`. The body is a pointer into `buf`.

This is what makes per-message processing cheap:

- Per-header parsing costs O(header length) once, then O(1) for every subsequent access.
- The total memory footprint is `len(message) + sizeof(parsed structs touched)`, not a multiplier of message size.
- Freeing the message at the end of the route is one operation: free `buf`, free the `sip_msg` and everything pkg-allocated under it.

But this also constrains what mutations look like. You **cannot** edit `msg->buf` in place — every parsed pointer would either become stale or have to be re-resolved. You **cannot** swap `buf` for a modified copy without invalidating every cached parse and every module that's already pulled a pointer.

The way Kamailio resolves this constraint — the way it lets you add, remove, and rewrite parts of the message without ever touching the buffer — is the **lump system**, which is the entire subject of the next chapter.

---

<p markdown="1" align="center">
  [← Table of contents](../) · [← 3.1 Reception](07-reception.md) · [Next: 3.3 Lumps →](09-lumps.md)
</p>
