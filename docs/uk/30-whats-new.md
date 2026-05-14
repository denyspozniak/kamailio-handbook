# 9.3 Що нового — і що в розробці

> [!IMPORTANT]
> Посібник націлений на **Kamailio 6.1.x** (stable-лінія, квітень 2026). Цей додаток перелічує помітні зміни між недавніми мажорними версіями, що було заархівовано, і де шукати, що відбувається у devel-гілці. Це навмисно *вказівник* — wiki й репо — авторитетні трекери.

## Швидка орієнтація у недавніх версіях

| Гілка | Статус (травень 2026) | Перший реліз | Що принесла |
|---|---|---|---|
| 6.1.x | **Поточний stable** | 2026-03-03 | 4 нові модулі, VRF у core, TLS domain match, SHA3-трансформації, нові RPC |
| 6.0.x | Maintained | 2025 | Перша 6.x-лінія — multi-threaded UDP receiving, CMake build, видалено 8 legacy-модулів |
| 5.8.x | Maintained (long-tail) | 2024 | Остання 5.x; багато продакшн-розгортань ще тут |
| `master` (devel) | → 6.2.x | — | Активна розробка; in-progress дивитися у GitHub-репо |

У Kamailio немає формального «LTS» — кожна `X.Y`-лінія maintained приблизно рік після релізу наступного мажора. На практиці оператори таргетять або поточний stable (6.1.x для нових), або одну лінію назад (6.0.x) для консервативності.

## Що додало 6.1.x

**Нові модулі**

| Модуль | Призначення |
|---|---|
| `auth_arnacon` | Автентифікація через Arnacon-протокол |
| `auth_web3` | Web3-style автентифікація (wallet-based identity) |
| `peerstate` | Tracking стану peer'ів по кластеру, доповнює dispatcher-liveness |
| `ptimer` | Process-level-таймери — більш гранулярний scheduling, ніж глобальний `timer` |

**Заархівовані модулі (переведено у `kamailio-archive`-репо)**

- `app_java`, `db_berkeley`, `db_perlvdb` — давно не використовувані інтеграції, які більше не виправдовували maintenance.

**Помітні зміни в core**

- Підтримка **VRF (Virtual Routing and Forwarding)** у core-визначеннях сокетів — bind'ити listener у конкретний Linux-VRF.
- **TLS connection domain matching** — обирати TLS-конфіг per-connection через SNI / SAN.
- **SHA3 / Keccak** — криптографічні трансформації, доступні у cfg DSL.
- Нові псевдо-змінні `$defv()`, `$defs()`, `$iuid` — runtime-доступ до defined-значень і per-instance UUID.
- RPC `modparam.getn`, `modparam.setn`, `modparam.list` — повноцінна інтроспекція й runtime-tweaking параметрів модулів (розділ 2.4 покрив `cfg.*`-сімейство; ці — узагальнення).
- TCP listen-backlog тепер налаштовується — корисно проти accept-storm.
- Покращення підтримки ARM64 — Kamailio чисто працює на graviton-class-інстансах.

## Що змінило 6.0.x (vs 5.x)

Це більший розрив. Якщо команда ще на 5.8.x і думає про стрибок — ось куди дивитися:

**Архітектурні зміни**

- **Multi-threaded UDP receiving** як опція — worker-модель (розділ 2.1) отримала гібридний режим, де один процес може використовувати кілька потоків для UDP `recvfrom`. Не замінює per-message-per-worker-патерн, але зменшує загальну кількість процесів для дуже високого PPS.
- **CMake build system** — замінює старий hand-rolled-Makefile. Новий інвок: `cmake -S . -B build && cmake --build build`. Старий `make`-workflow ще працює, але CMake тепер рекомендований.
- **TLS перемігрувало з OpenSSL ENGINE на provider keys** для OpenSSL 3.x. Зачіпає кастомні TLS-конфіги, що посилалися на ENGINE-ключі.

**Заархівоване у 6.0.x**

- `auth_identity`, `app_lua_sr`, `app_sqlang`, `app_mono` — застарілі scripting-bridge'і (Lua тепер через `app_lua`, Python — через `app_python3` і т.д.).
- `db_cassandra` — заміщено mainstream-DB-модулями; Cassandra-інтеграції тепер через зовнішні пайплайни.
- `osp`, `print`, `print_lib` — давно deprecated.

**Breaking-зміни конфіга**

- `dialog` прибрав підтримку старого параметра `dlg_flag` — state ставиться через `dlg_manage()`-прапори.
- `app_python3` видалив legacy compatibility shim'и; скрипти, що таргетили Kamailio 5.x, можуть потребувати дрібних правок.

## Що в розробці (`master`-гілка)

Гілка `master` у [github.com/kamailio/kamailio](https://github.com/kamailio/kamailio) — це місце, де формується 6.2.x. Сторінка wiki [kamailio.org/wikidocs/features/new-in-devel/](https://www.kamailio.org/wikidocs/features/new-in-devel/) — авторитетний живий список; оновлюється мейнтейнерами по мірі того, як фічі землять.

Як подивитися, що йде, без неї:

```bash
# Свіжі коміти у master
gh repo clone kamailio/kamailio && cd kamailio
git log --oneline master --since="3 months ago" | head -50

# Нові модулі у master vs останній stable-tag
git diff --name-status 6.1.2..master -- src/modules/ | grep '^A' | head -20

# Open PR з лейблом "feature"
gh pr list --repo kamailio/kamailio --label feature --state open
```

Mailing list `sr-dev@lists.kamailio.org` несе design-дискусії до того, як код потрапляє у tree; GitHub Discussions — для high-level-роадмеп-питань.

## Як розділи посібника співвідносяться з версіями

Посібник націлений на Kamailio 6.1.x, і архітектурні концепти стабільні через недавні версії. На що звертати увагу при читанні розділів на іншій версії:

- **Процесна модель** (2.1) — у 6.0+ додано опційний UDP-receiving-threading-режим, але multi-process-дисципліна без змін.
- **Пам'ять** (2.2) — вибір аллокатора і розкол `pkg`/`shm` не міняються відколи задовго до 5.x.
- **Lumps** (3.3) — data-lump-машинерія стабільна 15+ років. Source-файли все ще `data_lump.{c,h}`.
- **KEMI** (5) — `KSR.*`-API forward-compatible; нові біндинги додаються per-release без видалення старих.
- **Routing engine** (3.4) — `reply_route` і `onreply_route` обидва існують у кожній сучасній версії; перелік подій для `event_route[…]` зростає з кожним релізом, як модулі додають хуки.
- **`htable`, `dispatcher`, `dmq`** (8) — feature-surface зростає; описані архітектурні патерни без змін.

Якщо ви побачили поведінку, що суперечить посібнику на актуальній версії — **репо виграє**: посібник — best-effort, але C-код — авторитетний.

## Куди дивитися за розвитком Kamailio

- **GitHub-репо**: [kamailio/kamailio](https://github.com/kamailio/kamailio) — код, issues, PR.
- **Wiki**: [kamailio.org/wikidocs](https://www.kamailio.org/wikidocs/) — features-per-version-сторінки, документація модулів.
- **Mailing list'и**: `sr-users@` для ops-питань, `sr-dev@` для розробки.
- **Asipto blog** ([asipto.com](https://www.asipto.com/blog/)) — компанія, що рухає багато з комерційної розробки Kamailio; пости про нові фічі й roadmap.
- **Щорічна конференція KamailioWorld** — реліз-recap'и й roadmap-доповіді.

---

<p markdown="1" align="center">
  [← Зміст](../) · [← 9.2 Карта термінів](28-term-map.md)
</p>
