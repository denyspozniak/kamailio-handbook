<h1 align="center">Kamailio Handbook</h1>

<p align="center">
  <em>An architecture-focused, bilingual deep-dive into the Kamailio SIP server.</em>
</p>

<p align="center">
  <img alt="Kamailio" src="https://img.shields.io/badge/Kamailio-5.8.x-1f6feb?style=flat-square&logo=asterisk&logoColor=white">
  <img alt="Languages" src="https://img.shields.io/badge/docs-EN%20%7C%20UK-238636?style=flat-square">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-6e7681?style=flat-square"></a>
  <a href="https://github.com/denyspozniak/kamailio-handbook/commits/main"><img alt="Last commit" src="https://img.shields.io/github/last-commit/denyspozniak/kamailio-handbook?style=flat-square&color=bf8700"></a>
</p>

<p align="center">
  <a href="docs/en/README.md"><img alt="Read in English" src="https://img.shields.io/badge/Read-English-1f6feb?style=for-the-badge&logo=readthedocs&logoColor=white"></a>
  &nbsp;
  <a href="docs/uk/README.md"><img alt="Читати українською" src="https://img.shields.io/badge/Читати-Українською-bf8700?style=for-the-badge&logo=readthedocs&logoColor=white"></a>
</p>

---

> [!NOTE]
> This is **not** a replacement for the official Kamailio documentation. It's a companion that goes deep on the *how* and the *why* — internal machinery, design rationale, and architectural patterns operators actually need to reason about production behaviour.

## Where Kamailio sits

```mermaid
flowchart LR
    UAC([SIP UAC<br/>phones · softphones · WebRTC])
    Kam[["Kamailio<br/>signalling"]]
    RTP[["RTPEngine<br/>media plane"]]
    DB[("Database<br/>MySQL · PostgreSQL")]
    UAS([SIP UAS<br/>PBX · gateways · trunks])

    UAC == SIP ==> Kam
    Kam == SIP ==> UAS
    UAC -. RTP .-> RTP
    RTP -. RTP .-> UAS
    Kam <--> DB
    Kam -. control .-> RTP

    classDef signal fill:#1f6feb,stroke:#1f6feb,color:#fff
    classDef media fill:#bf8700,stroke:#bf8700,color:#fff
    classDef store fill:#6e7681,stroke:#6e7681,color:#fff
    classDef endpoint fill:#238636,stroke:#238636,color:#fff

    class Kam signal
    class RTP media
    class DB store
    class UAC,UAS endpoint
```

Kamailio handles **signalling only** — call setup, routing, registration, authentication. Media flows around it through a separate engine (typically [RTPEngine](https://github.com/sipwise/rtpengine)). Understanding this split is the foundation for everything else in this handbook.

## What's inside

<table>
  <thead>
    <tr><th align="left">#</th><th align="left">Chapter</th><th align="left">English</th><th align="left">Українська</th></tr>
  </thead>
  <tbody>
    <tr><td>1</td><td><b>Preface</b> — what Kamailio is, the minimum to follow along</td><td><a href="docs/en/README.md#1-preface">EN</a></td><td><a href="docs/uk/README.md#1-передмова">UK</a></td></tr>
    <tr><td>2</td><td><b>Architecture</b> — the main focus: process model, request pipeline, modules, state, transport</td><td><a href="docs/en/README.md#2-architecture-main-focus">EN</a></td><td><a href="docs/uk/README.md#2-архітектура-основний-фокус">UK</a></td></tr>
    <tr><td>3</td><td><b>Configuration patterns</b> — routing logic, pseudo-vars, transformations</td><td><a href="docs/en/README.md#3-configuration-patterns">EN</a></td><td><a href="docs/uk/README.md#3-патерни-конфігурації">UK</a></td></tr>
    <tr><td>4</td><td><b>Key modules</b> — architectural deep-dives into <code>tm</code>, <code>dialog</code>, <code>dispatcher</code>, <code>rtpengine</code>, <code>registrar</code></td><td><a href="docs/en/README.md#4-key-modules-architectural-deep-dives">EN</a></td><td><a href="docs/uk/README.md#4-ключові-модулі-архітектурні-розбори">UK</a></td></tr>
    <tr><td>5</td><td><b>Deployment patterns</b> — registrar, outbound proxy, LB, WebSocket gateway</td><td><a href="docs/en/README.md#5-deployment-patterns">EN</a></td><td><a href="docs/uk/README.md#5-патерни-розгортання">UK</a></td></tr>
    <tr><td>6</td><td><b>Operations</b> — logging, monitoring, troubleshooting from first principles</td><td><a href="docs/en/README.md#6-operations-architecture-aware">EN</a></td><td><a href="docs/uk/README.md#6-експлуатація-з-урахуванням-архітектури">UK</a></td></tr>
    <tr><td>7</td><td><b>Reference</b> — pseudo-variables, RPC commands, glossary</td><td><a href="docs/en/README.md#7-reference">EN</a></td><td><a href="docs/uk/README.md#7-довідник">UK</a></td></tr>
  </tbody>
</table>

## Conventions

> [!TIP]
> Each chapter lives in **both** `docs/en/` and `docs/uk/` under the same filename. If you fix a typo in one tree, please mirror it in the other.

- **Diagrams** use [Mermaid](https://mermaid.js.org/) — renders natively on GitHub, diff-friendly, no binary assets.
- **Code blocks** are tagged with language (`kamailio`, `bash`, `sql`) for syntax highlighting.
- **Callouts** (`> [!NOTE]`, `> [!TIP]`, `> [!WARNING]`) flag the parts you can't skim past.

## Sources

| Priority | Source | Used for |
|---|---|---|
| 1 | [jiriatipteldotorg/kamailio-doc](https://jiriatipteldotorg.github.io/kamailio-doc/) | Backbone — chapter structure and coverage |
| 2 | [kamailio.org/wikidocs](https://www.kamailio.org/wikidocs/) | Filling gaps, operational know-how |
| 3 | [github.com/kamailio/kamailio](https://github.com/kamailio/kamailio) | Source of truth for edge cases and subtle behaviour |

## License

[MIT](LICENSE) — use it, fork it, translate it.
