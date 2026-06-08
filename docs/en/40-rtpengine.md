# 8.6 Media — rtpengine and the RTP path

> [!IMPORTANT]
> Everything so far moved *signalling*. Kamailio never touches `RTP` — media flows endpoint-to-endpoint, and a SIP proxy has no business in that path. Except when it does: NAT, encryption mismatches, and topology hiding all force you to anchor media on a relay. `rtpengine` is that relay, and you drive it entirely from the routing script. This is how the media plane attaches to the signalling one.

## Why a media relay at all

Kamailio routes `INVITE`s and rewrites SDP, but `RTP`/`RTCP` go straight between the user agents — it is a signalling box, not a media one. Two endpoints behind different NATs can't reach each other directly: the addresses in their SDP are private. So you drop a publicly reachable relay in the middle, rewrite each side's SDP `c=`/`m=` to point at it, and it forwards the streams. The same anchor buys more: media-side topology hiding (neither end learns the other's address), call recording, codec transcoding, and — the one that matters most here — a crypto gateway between endpoints that don't share a media security profile.

`rtpproxy` was the original, driven the same way through Kamailio's `rtpproxy` module. `rtpengine` (sipwise) superseded it with SRTP/DTLS, transcoding, ICE, and in-kernel forwarding. Treat `rtpproxy` as the legacy minimal relay and `rtpengine` as the default.

## Steering it from the config

The `rtpengine` module talks to the daemon over the **ng protocol** — bencoded dictionaries over UDP, deliberately incompatible with the old rtpproxy control protocol. Point it at one or more daemons:

```
modparam("rtpengine", "rtpengine_sock", "udp:127.0.0.1:12221")
# weighted instances, or named sets:
modparam("rtpengine", "rtpengine_sock", "1 == udp:10.0.0.1:12221 udp:10.0.0.2:12221")
```

Three functions map onto the SDP offer/answer handshake:

- `rtpengine_offer()` on the inbound `INVITE` — rewrites the offer SDP, allocates the relay ports.
- `rtpengine_answer()` on the `200 OK` — rewrites the answer with the matching ports.
- `rtpengine_delete()` on `BYE`/failure — frees the session.

In practice you call `rtpengine_manage()`, which picks offer/answer/delete from the method and direction, so one line covers the common case. Behaviour is a flag string on the call — `replace-origin replace-session-connection ICE=remove RTP/AVP …` — and `set_rtpengine_set(N)` chooses which daemon set handles it. The session is keyed by `Call-ID`; rtpengine holds the port, crypto, and learning state, while Kamailio only nudges it at offer, answer, and teardown.

## RTP bleed and `strict source`

A relay opens a public UDP port pair per stream, and to survive symmetric NAT it *latches*: it learns the real peer address from the first inbound `RTP` it sees, then forwards there. That learning is the hole. **RTP bleed** (the 2017 rtpbleed class) is an attacker scanning your media range and firing `RTP` at an open port; the relay latches onto the attacker's source and starts copying the victim's audio to them — passive eavesdropping — or lets them inject media into the call. No signalling, no auth, just a guessed open port.

The mitigation is the **`strict source`** flag: after the endpoint is learned, rtpengine keeps comparing every packet's source address and port against it and *drops* mismatches instead of re-latching. Its opposite, `media-handover`, re-learns and moves to the new address — right for genuine mobility, exactly wrong where bleed is a concern, so keep it off the public edge. Back `strict source` with a firewalled, non-scannable media port range and the edge filtering of [9.1](36-security-surface.md): the port still exists, you are just refusing to follow it anywhere the signalling didn't promise.

## SRTP, DTLS, and the WebRTC bridge

rtpengine terminates media crypto and gateways the *transport profile* between legs — which is what lets a plain-RTP SIP phone talk to an encrypted WebRTC browser in one call. You request the profile per leg by rewriting the SDP transport in the offer/answer flags:

- `RTP/AVP` — plain RTP. `RTP/SAVP` — SRTP keyed by SDES (keys in the SDP `a=crypto`). `RTP/AVPF` / `RTP/SAVPF` — the feedback profiles. `UDP/TLS/RTP/SAVPF` — DTLS-SRTP, the WebRTC transport.
- `DTLS=passive|active|off` picks the DTLS handshake role; the `SDES` family tunes or disables SDES and orders crypto suites.

A WebRTC↔SIP call is therefore one rtpengine session bridging two profiles: toward the browser you offer `UDP/TLS/RTP/SAVPF` with DTLS; toward the SIP leg you rewrite to `RTP/AVP`. rtpengine terminates DTLS-SRTP on the browser side, decrypts, and emits plain RTP to the phone — re-encrypting the return path. The same mechanism downgrades an SRTP-only trunk to a plain-RTP core, or the reverse.

## ICE and STUN

WebRTC also requires ICE, and rtpengine is a full ICE agent — which means it speaks **STUN**: it gathers candidates and answers the STUN binding (connectivity-check) requests the browser fires to probe the path, so ICE completes against the relay itself rather than the far endpoint. You steer it with the `ICE` flag: `ICE=force` synthesises a fresh candidate set toward an endpoint (add ICE for a browser), `ICE=remove` strips ICE toward a UA that can't do it (a plain SIP phone), `ICE=optional` (default) keeps whatever is there. That is the other half of the bridge: `ICE=force` + `DTLS` + `UDP/TLS/RTP/SAVPF` toward the browser, `ICE=remove` + `RTP/AVP` toward the phone.

## Kernel mode — how packets bypass the daemon

A relay's cost is per-packet: a busy box moves millions of `RTP` packets a second, and a userspace copy per packet caps you early. rtpengine avoids it with a kernel module.

The daemon handles the ng control protocol and the *first* packets of each stream in userspace — that is where latching, ICE, and the DTLS handshake happen. Once a stream is confirmed (both ends learned), the daemon installs a forwarding entry into the **`xt_RTPENGINE`** kernel module's table. Interception is an iptables rule over the media range:

```
iptables -I INPUT -p udp -j RTPENGINE --id 0
```

The `RTPENGINE` target (matched to the daemon's `--table 0`) hands each inbound UDP packet to the kernel module, which looks it up in the in-kernel forwarding table: a **hit** is rewritten — address swap, plus SRTP decrypt/encrypt for an encrypted stream — and sent back out entirely in kernel, never copied to userspace; a **miss** falls through to the daemon (a new flow or a control packet). With the module unloaded, everything falls back to userspace automatically.

The payoff: steady-state media is a kernel forwarding-table lookup, and the daemon only ever sees setup, teardown, and the occasional new flow — tens of thousands of concurrent calls on one box. The streams that *can't* go to the kernel are the ones that need every packet in userspace: recording and transcoding.

---

<p markdown="1" align="center">
  [← Table of contents](../) · [← 8.5 dmq](23-dmq.md) · [Next: 8.7 Capturing SIP over TLS →](41-siptrace.md)
</p>
