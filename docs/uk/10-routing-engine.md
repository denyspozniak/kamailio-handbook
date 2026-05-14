# 3.4 Движок маршрутизації

> [!IMPORTANT]
> Routing-движок — це те, що робить Kamailio *Kamailio*. Усе попереднє — процесна модель, пам'ять, lumps — це сантехніка. Движок — це місце, де ваш `kamailio.cfg` стає виконуваною поведінкою, де повідомлення зустрічається з наміром оператора, і де живе більша частина повсякденної ментальної моделі «що цей сервер зараз робить».

## Route'и пре-компілюються, а не інтерпретуються per-message

Коли Kamailio стартує, cfg-парсер читає `kamailio.cfg` і будує in-memory **AST** кожного route-блока, кожного `if/else`, кожного виклику функції. Цей AST запечатується наприкінці `mod_init()` і більше ніколи не змінюється у рантаймі.

Per-message-виконання — це обхід дерева, а не інтерпретація скрипта. Ціна `if (is_method("INVITE"))` — це порівняння і branch — без жодного парсера в рантаймі, без жодних string-lookup'ів. Саме тому per-message-overhead «від скрипта» в Kamailio мінімальний: він виконує пре-компільовані інструкції, а не інтерпретує сирці.

> [!NOTE]
> Саме тому зміни в `kamailio.cfg` потребують повного рестарту (див. [розділ 2.4](05-lifecycle.md)). AST уже форкнутий у кожен воркер, запечений у регістрації функцій модулів, інлайнений у виконавчий шлях. Шляху перепарсити і підмінити на льоту не існує.

## Які бувають route-блоки і коли вони стріляють

У Kamailio є кілька різних типів route'ів. Кожен викликається рантаймом у конкретний момент життєвого циклу повідомлення:

```mermaid
flowchart TD
    Recv["receive_msg()"] --> Type{це reply?}
    Type -- запит --> RR["request_route<br/>(entry point)"]
    Type -- відповідь --> OR["onreply_route<br/>(кожна відповідь)"]

    RR --> Decide{дія}
    Decide -- forward stateless --> Send["lumps застосовано → send"]
    Decide -- t_relay --> TM["tm: створити txn"]
    Decide -- t_reply --> Reply["побудувати reply<br/>+ lumps застосовано → send"]
    Decide -- drop / exit --> End[(кінець)]

    TM --> BR["branch_route[N]<br/>per branch, перед send'ом"]
    BR --> Send

    Send -.-> Resp[прилетіла відповідь]
    Resp --> OR2["onreply_route[N]<br/>per-txn onreply"]
    OR2 --> Decision2{клас відповіді}
    Decision2 -- 2xx final --> Relay["relay назад до UAC"]
    Decision2 -- 4xx-6xx --> FR["failure_route[N]<br/>можна re-fork'нути"]
    FR --> TM
    Decision2 -- 1xx provisional --> Resp

    classDef route fill:#1f6feb,stroke:#1f6feb,color:#fff
    classDef sys fill:#6e7681,stroke:#6e7681,color:#fff
    classDef end_ fill:#238636,stroke:#238636,color:#fff
    class RR,OR,BR,OR2,FR route
    class Recv,TM,Send,Resp,Decide,Decision2,Type sys
    class End end_
    class Reply,Relay end_
```

**`request_route`** — entry point для кожного вхідного **запиту**. Тут живе більшість того, що люди розуміють під «конфігом Kamailio»: routing-рішення, аутентифікація, rewrite, виклик `t_relay()` чи `forward()`. Існує рівно один `request_route`-блок.

**`reply_route`** — стріляє у **core'овому reply-processing-шляху** для *кожної* вхідної відповіді, до того, як tm спробує зматчити її з транзакцією. Корисно для інспекції чи короткого замикання відповідей незалежно від transaction-стану — дропнути malformed-відповідь, лічити метрики на wire-рівні, застосувати політику, що не потребує transaction-контексту. Повернути `0` (drop) з `reply_route` — повністю зупиняє подальшу обробку. Відрізняється від `onreply_route`: цей бігає незалежно від того, чи відповідь належить активній транзакції.

**`onreply_route`** — бігає як частина tm transaction processing, після того, як tm зматчив вхідну відповідь з транзакцією у shm. Голий `onreply_route { … }` беззастережно для matched-відповідей; іменовані `onreply_route[N]` — лише для відповідей транзакцій, що opt-in'ули через `t_on_reply("N")`. Іменовані — спосіб перехопити відповідь конкретного виклику (SDP rewriting, accounting на 200 OK тощо).

> [!TIP]
> Ментальна модель: `reply_route` — **wire-level** (кожен байт, що виглядає як відповідь), `onreply_route` — **transaction-level** (відповіді, що належать `tm`-cell'у). У stateful-проксі з `tm`-усюди більшість reply-логіки живе у `onreply_route`. `reply_route` — правильне місце для фільтрації, rate-limiting'у чи stateless-відповідей, що оминають `tm`.

**`branch_route[N]`** — бігає **один раз на branch**, прямо перед тим, як вихідне повідомлення цього branch'а буде побудоване і відправлене. Тут лежать per-branch-модифікації: різний Record-Route per branch, branch-specific заголовки, рішення на основі того, який gateway буде у branch'а. Активується через `t_on_branch("N")` перед `t_relay()`.

**`failure_route[N]`** — бігає, коли branch видав final negative response (4xx-6xx) або зніс по таймауту. Усередині скрипт може **re-fork'нути** транзакцію на інший destination (поширений патерн: failover на secondary gateway), побудувати кастомну відповідь через `t_reply()`, або просто дати failure поширитися. Активується через `t_on_failure("N")`.

**`event_route[<event-name>]`** — бігає у відповідь на runtime-події, які *не* прив'язані до повідомлення з дроту. Поширені: `event_route[tm:branch-failure]` для branch-specific-failure-хуків, `event_route[xhttp:request]` для HTTP-over-SIP-socket-запитів, `event_route[dispatcher:dst-down]` коли gateway помічений мертвим. Кожен модуль експозить свої події.

**`send_route`** — викликається безпосередньо перед тим, як будь-яке повідомлення піде на дріт. Використовуйте економно; бігає поверх уже побудованого outbound-повідомлення, і робити там осмислену роботу — дорого.

## Cfg як DSL — що це насправді

Конфігурайційна мова — не general-purpose-скриптинг. Це domain-specific-діалект, що існує заради одного: добре виражати SIP routing decisions поверх розпарсеного повідомлення.

Що в ньому є:
- **Control flow** — `if/else`, `switch/case`, `while`, `break`, `return`, `exit`, `drop`.
- **Оператори порівняння** разом із regex (`=~`, `!~`).
- **String operations** через псевдо-змінні й трансформації.
- **Виклики функцій** — module-exported функцій (`t_relay()`, `record_route()`, `is_method("INVITE")`).
- **Виклик sub-route** — `route("auth")` викликає інший route-блок, ділиться `sip_msg`'ом.

Чого свідомо немає:
- **Довільних обчислень.** Жодної арифметики поза тим, що дають псевдо-змінні-трансформації. Жодних власних структур даних.
- **Loop'ів по колекціях.** Не можна ітерувати заголовки; можна перевіряти лише іменовані.
- **Рекурсії.** Sub-route'и можуть викликати інші sub-route'и, але глибина обмежена.
- **Closure'ів, модулів, чи будь-чого, що ви б знайшли в справжній мові.**

Це фіча, не обмеження. Обмеження роблять мову tractable для reasoning'у (один route, один шлях, обмежена глибина) і роблять кожну операцію дешевою (жодних динамічних алокацій per loop, жодних name-lookup'ів у рантаймі). Коли потрібні справжні обчислення — credit-чеки, складні routing-таблиці, HTTP-запити — ви виходите в модуль або в KEMI (розділ 5), що вбудовує повний інтерпретатор саме для таких випадків.

## Sub-route'и і як route'и взаємодіють

`route("name")` викликає іменований sub-route — просто інший route-блок, оголошений як `route[name] { … }`. Sub-route бігає з тим самим `sip_msg`, тим самим станом `$var(...)`, тими самими псевдо-змінними. Жодної function-call-ізоляції — це фактично textual inclusion, відкладене до рантайму.

```kamailio
request_route {
    route("sanity");
    route("auth");
    route("routing");
}

route[auth] {
    if (!is_present_hf("Authorization")) {
        auth_challenge("$fd", "0");
        exit;
    }
}
```

`return` з sub-route'а повертає в caller. `exit` будь-звідки закінчує обробку для цього повідомлення цілком. `drop` — це `exit` плюс хінт для `tm`, що транзакцію треба «з'їсти» тихо, а не відповідати.

## Як route'и взаємодіють із lumps

Ключове спостереження: кожен route-блок бігає на **тому самому `sip_msg`**, і lump-список — це поле цього структу. Модифікації, зроблені в `request_route`, видимі (як lumps у черзі) у `branch_route`. Lumps, поставлені в чергу у `branch_route`, застосовуються лише до вихідного повідомлення цього branch'а. Lumps, поставлені в `onreply_route`, застосовуються до відповіді, що фор'юардиться назад.

Саме тому `branch_route` — правильне місце для per-destination-кастомізації: побудова вихідного повідомлення кожного branch'а бачить об'єднання `request_route`'их lumps плюс branch'ові lumps. Вони не зливаються в один список — applier композить їх у момент send'у.

## Implicit drop

Тонке, але важливе правило: якщо `request_route` закінчив виконання без явного форвардингу (`t_relay`, `forward`, `t_reply`), Kamailio **тихо дропає повідомлення**. Жодного implicit-форвардингу не існує — скрипт мусить вирішити.

Це неінтуїтивно при першому знайомстві з cfg DSL. Люди очікують «я ж не сказав дропати — то воно ж мало б форвардитися». Працює навпаки: нічого не форвардиться, поки ви не сказали.

Наступний розділ бере routing-рішення, зроблені цим движком, і проводить їх через реальну передачу — як lumps застосовуються, як stateful vs stateless відрізняються у момент send'у, як відповіді знаходять дорогу назад.

---

<p markdown="1" align="center">
  [← Зміст](../) · [← 3.3 Lumps](09-lumps.md) · [Далі: 3.5 Форвардинг і відповіді →](11-forwarding.md)
</p>
