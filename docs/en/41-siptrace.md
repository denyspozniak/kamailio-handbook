# 8.7 Capturing SIP over TLS — siptrace and HEP

> [!IMPORTANT]
> The moment you turn on TLS (`5061`) or WebSocket-Secure, `tcpdump` and `sngrep` on the wire go blind — they see TLS records, not SIP. The trick every operator eventually needs: stop capturing on the wire and capture *inside* Kamailio, where the message is already plaintext, streaming a copy out over HEP. `siptrace` does exactly that, and `sngrep` renders it live.

## Why wire capture fails on TLS

TLS is terminated at the transport layer — the `tls` module decrypts the byte stream during reception ([3.1](07-reception.md)), *before* the parser and `request_route` ever see it. So the `sip_msg` Kamailio routes on is plaintext no matter the transport. On the NIC, a `5061` or WSS flow is an opaque TLS record stream: `sngrep` can't parse it, and pulling session keys off a busy proxy to decrypt offline is not a debugging workflow. For encrypted signalling, wire capture is dead — you have to tap a layer up.

## siptrace — tap at the SIP layer

`siptrace` duplicates the message as Kamailio sees it: after decrypt, before re-encrypt, so the copy is always plaintext. Two ways to arm it — per-message `sip_trace()` in the route (selective: trace only what a condition matches) or `trace_mode`/`trace_on` for automatic global mirroring; `sip_trace_mode()` (or the mode arg) sets the scope to message, transaction, or dialog.

Where the copy goes is modparams:

- `trace_mode` — bit-flags for the destination: `1`=HEP, `2`=database, `4`=SIP URI.
- `duplicate_uri` — the target as a SIP URI, e.g. `sip:127.0.0.1:9060`.
- `hep_mode_on` — wrap the copy in HEP; `hep_version` (`1`/`2`/`3`); `hep_capture_id` tags this agent.
- `trace_to_database` — also write to the `sip_trace` table for offline/Homer storage.

## HEP — why not just forward the SIP

HEP (Homer Encapsulation Protocol) wraps the original SIP payload *plus metadata* — source/destination IP:port, transport, timestamp, and a correlation/capture id — in a UDP envelope. The metadata is the whole point: the decrypted copy has lost its real transport identity (it now originates from Kamailio), so HEP carries the *original* 5-tuple alongside the payload, and the correlation id stitches both legs of a call together. Homer/sipcapture is the long-term store; for live debugging you don't need it — any HEP listener will do.

## Viewing it live with sngrep

`sngrep` speaks HEP both ways. Point `siptrace` at a local port:

```
modparam("siptrace", "trace_mode", 1)                 # 1 = HEP
modparam("siptrace", "hep_mode_on", 1)
modparam("siptrace", "duplicate_uri", "sip:127.0.0.1:9060")
```
```
request_route {
    sip_trace();      # duplicate this (decrypted) message over HEP
    ...
}
```

Then run `sngrep` as a HEP listener on that port and watch the decrypted dialogs — ladder diagram and full message bodies — even though the wire carried TLS:

```
sngrep -L udp:127.0.0.1:9060
```

`-L` (`--eep-listen`) starts the HEP server; `-H udp:homer.example.net:9060` (`--eep-send`) re-emits the same stream onward to a Homer instance or a second `sngrep` (older builds spell these EEP options `--eep` / `-E`). One capture point, decrypted, forwardable.

## When to reach for it

TLS/WSS is the obvious case, but tapping inside also wins where the wire lies in other ways: you see the message *after* your own lump edits (the final form actually sent), you see both sides of a topology-hidden call (`siptrace` sits inside, where `topos` hasn't masked anything yet), and the HEP correlation id lets you follow one call across a cluster. The cost is one duplicated UDP packet per traced message — cheap, but on heavy traffic keep `sip_trace()` behind a condition rather than mirroring everything.

---

<p markdown="1" align="center">
  [← Table of contents](../) · [← 8.6 Media — rtpengine](40-rtpengine.md) · [Next: 7.1 RPC architecture →](24-rpc-architecture.md)
</p>
