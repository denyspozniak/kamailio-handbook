<h1 align="center">Kamailio Handbook — Українська</h1>

<p align="center">
  <em>Як Kamailio влаштований зсередини.</em>
</p>

<p align="center">
  <img alt="Kamailio" src="https://img.shields.io/badge/Kamailio-5.8.x-1f6feb?style=flat-square">
  <img alt="Мова" src="https://img.shields.io/badge/мова-Українська-bf8700?style=flat-square">
  <a href="../en/README.md"><img alt="Switch to English" src="https://img.shields.io/badge/switch_to-English-1f6feb?style=flat-square"></a>
</p>

---

> [!IMPORTANT]
> Цей посібник **свідомо не переказує офіційну документацію**. Передбачається, що ви вже знаєте, що таке Kamailio на поверхні. Натомість тут — занурення в рантайм, життєвий цикл повідомлень, движок скриптів, KEMI та архітектурні фішки, які формують поведінку Kamailio. Розділу «модуль за модулем» тут не буде.

## Як SIP-запит проходить через Kamailio

```mermaid
flowchart LR
    In([SIP IN]) --> Parser[Парсер]
    Parser --> Sanity[Sanity-перевірки]
    Sanity --> RR[request_route]
    RR --> Mods[[Функції модулів<br/>tm · rr · auth · dispatcher · …]]
    Mods --> Decision{Stateful?}
    Decision -- так --> TM[tm: створити транзакцію]
    Decision -- ні --> SL[sl: stateless-форвард]
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

Одне отримане SIP-повідомлення проходить через цей конвеєр. Більшість того, що в конфізі Kamailio виглядає «магічно», — це просто вибір гілки на цьому шляху. Цей посібник розбирає кожен прямокутник вище.

## Зміст

### 1. Передмова
- [1.1 Вступ](01-introduction.md) — сигналізація проти медіа, ментальна модель, чого чекати ✅

### 2. Рантайм
- 2.1 Процесна модель — main, attendant, timer, воркери: для чого кожен
- 2.2 Архітектура пам'яті — `pkg` vs `shm`, кастомний алокатор, правила життєвого циклу
- 2.3 Примітиви конкурентності — локи, atomic-операції, lockless-шляхи
- 2.4 Життєвий цикл — старт, перезавантаження конфігу, graceful shutdown

### 3. Життєвий цикл SIP-повідомлення
- 3.1 Прийом — сокети, слухачі, як транспорт демультиплексує
- 3.2 Стратегія парсингу — lazy headers, що парситься і коли, ціна
- 3.3 Движок маршрутизації — `request_route`, `branch_route`, `failure_route`, `onreply_route`, `event_route`
- 3.4 Форвардинг і відповіді — що насправді відбувається, коли повідомлення йде назовні

### 4. Движок скриптів
- 4.1 Cfg як DSL — навіщо власна мова, що вона оптимізує
- 4.2 Парсинг, AST, виконання — від `kamailio.cfg` до байткоду на повідомлення
- 4.3 Виклик функцій модулів — FFI між C і скриптом
- 4.4 Псевдо-змінні як рівень непрямості — як насправді працюють `$var(x)`, `$avp(y)`, `$hdr(z)`

### 5. KEMI — embedded scripting
- 5.1 Яку проблему вирішує KEMI
- 5.2 Bridge — як Lua, Python, JS, Ruby вбудовуються в C-рантайм
- 5.3 Життєвий цикл — коли запускається KEMI, що бачить, як стан перетинає кордон
- 5.4 Tradeoffs — коли виграє KEMI, коли native cfg

### 6. Стан, транзакції, діалоги
- 6.1 Транзакції (`tm`) — хеш-таблиці у shm, timer wheels, retransmission
- 6.2 Діалоги — як `dialog` доповнює `tm` для відстеження повного виклику
- 6.3 In-memory кеші з DB-синхронізацією — патерн `usrloc`

### 7. Control plane
- 7.1 Архітектура RPC — JSON-RPC, BINRPC, експорт команд
- 7.2 `kamcmd` — важіль оператора
- 7.3 Event routes — програмовані хуки в життєвий цикл рантайму

### 8. Архітектурні фішки
- 8.1 Topology hiding (`topos`) — переписування виклику так, щоб топологія зникла
- 8.2 Async-транзакції — `t_suspend` / `t_continue` для неблокуючих сценаріїв
- 8.3 `htable` — хеш-таблиці у спільній пам'яті як «бідний Redis»
- 8.4 `dispatcher` — hash-based stickiness, набори шлюзів, failover-алгоритми
- 8.5 `dmq` — синхронізація стану між інстансами Kamailio

### 9. Довідник
- 9.1 Глосарій ролей процесів
- 9.2 Карта термінів

---

<p align="center">
  <a href="../en/README.md">🇬🇧 English</a> · <a href="../../README.md">↑ На головну</a>
</p>
