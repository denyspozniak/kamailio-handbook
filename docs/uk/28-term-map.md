# 9.2 Карта термінів

Швидкий глосарій Kamailio-specific термінів, що зустрічаються в посібнику. SIP-протокольні (UAC, UAS, INVITE тощо) вважаються відомими з RFC 3261.

| Термін | Означає |
|---|---|
| **AOR** | Address Of Record — SIP-ідентичність (`alice@example.com`), під якою реєструються контакти. |
| **AVP** | Attribute-Value Pair — script-accessible іменована змінна, прив'язана до транзакції чи branch'а. Переживає async suspend/resume. |
| **branch** | Один destination у forked-транзакції. Кожен branch має свій вихідний буфер, lump-set, retransmission-стан. |
| **BINRPC** | Бінарний RPC-протокол через Unix-сокет. Дефолтний транспорт для `kamcmd`. |
| **cell** | `tm`-транзакція-record у shm. Тримає branch'і, таймери, refcount, хуки. |
| **cfg DSL** | Мова конфігурації: `kamailio.cfg`. Пре-компілюється в AST на старті, виконується per message. |
| **child_init()** | Хук модуля, що біжить раз на воркера після fork'у. Тут піднімаються per-process-ресурси (interpreter, DB-з'єднання). |
| **contact** | SIP `Contact` URI — binding AOR'у до конкретного endpoint'а. |
| **dialog** | Call-level state-record, що проходить через кілька транзакцій. Підтримується модулем `dialog`. |
| **dispatcher set** | Іменована, нумерована група destination'ів зі своїм алгоритмом і probing-конфігом. |
| **dmq** | Distributed Message Queue. Peer-to-peer-replication-мережа між кількома Kamailio-інстансами. |
| **FFI** | Foreign Function Interface — C-to-script-bridge, що KEMI використовує для диспетчеризації в Lua/Python/JS/Ruby. |
| **htable** | Generic shm hash-table, «бідний Redis». |
| **KEMI** | Kamailio Embedded Interface. Механізм писання routing'у на Lua, Python, JS, Ruby. |
| **`KSR.*`** | Глобальний namespace, експонований в KEMI-скриптах. `KSR.tm.t_relay()` дзвонить зареєстровану C-функцію. |
| **lump** | Queued message-мутація (add чи delete байтів на offset'і). Застосовується одним проходом на send'і. |
| **mod_init()** | Хук модуля, що біжить раз у main-процесі, до fork'у. Тут виділяється shm і реєструються RPC-команди. |
| **pkg** | Per-worker приватна купа. Lifetime — одне повідомлення; невидима іншим воркерам. |
| **pseudo-variable** | Script-side getter/setter на `sip_msg` чи runtime-state. Імена з `$` — `$ru`, `$tu`, `$hdr(X)`, `$var(x)`, `$shv(x)`. |
| **rank** | Цілий ID forked-воркера. Використовується для RNG-seed'у, вибору timer-слотів, log-disambiguation. |
| **RPC** | Remote Procedure Call. Runtime-introspection/control-API Kamailio. Через BINRPC і JSON-RPC. |
| **`sip_msg`** | C-struct з розпарсеним повідомленням: оригінальний буфер, header-список, тіло, lump-списки, прапори. Живе у pkg, один на воркера на повідомлення. |
| **shm** | Спільна пам'ять — один `mmap()`-нутий регіон, доступний з кожного воркера. Lifetime проходить через повідомлення і воркерів. |
| **`$shv`** | Shared variable. Іменована global у shm. |
| **`$sht`** | htable-accessor. `$sht(table=>key)` читає/пише entry. |
| **t_continue()** | Відновити раніше-suspend'нуту транзакцію з результатом. |
| **t_relay()** | Stateful-форвард запиту через `tm`. Створює транзакцію. |
| **t_suspend()** | Поставити поточну транзакцію на паузу, відпустити воркера, дозволити асинхронне resume пізніше. |
| **tm** | Transaction Module. Трекає SIP-транзакції в shm, керує retransmission'ом і форкингом. |
| **topos** | Topology-hiding-модуль. Переписує повідомлення так, щоб проксі був невидимий ендпоінтам. |
| **transaction** | SIP-запит плюс усі його відповіді, включно з retransmission'ами. Одиниця стану в `tm`. |
| **usrloc** | User Location-модуль. Контакт-кеш реєстратора з опційним DB-backing'ом. |
| **WAIT-таймер** | Per-transaction-таймер, що linger'ить після final-відповіді, поглинаючи retransmission'и до cleanup'у. |
| **wheel (timer)** | Time-bucketed-масив, що використовує timer-процес tm. O(1) на schedule, O(K) per tick де K — expirations. |

## Нотаційні конвенції в код-прикладах

- `something()` — функція модуля, callable з cfg.
- `$xx` чи `$xx(arg)` — псевдо-змінна, evaluated проти поточного `sip_msg`.
- `kamcmd <method>` — BINRPC-команда з host-shell.
- `event_route[<name>]` — runtime-хук, диспетчеризований рантаймом, а не вхідним повідомленням.
- `KSR.<module>.<function>` — KEMI-side-виклик у зареєстровану C-функцію.

## Де покрита кожна концепція

| Якщо ви плутаєтесь у… | Дивіться |
|---|---|
| Чому стільки процесів | Розділ 2.1 |
| Чому `$var` не переживає повідомлень | Розділ 2.1, 2.2 |
| Чому `remove_hf` не одразу видаляє заголовок | Розділ 3.3 |
| Чому `kamailio.cfg` не можна reload'нути | Розділ 2.4 |
| Чому Lua-global'и не шарені між воркерами | Розділ 5.3 |
| Чому `dispatcher.reload` посеред виклику може зсунути stickiness | Розділ 8.4 |
| Чому dmq «eventually consistent» | Розділ 8.5 |
| Чому `kamcmd` короткий, але всемогутній | Розділ 7.2 |

Це завершує посібник. Наступного разу, коли в продакшні щось виглядатиме дивно, шлях такий: чекніть `kamcmd` (розділ 7.2), почитайте відповідний розділ про задіяну машинерію, а якщо потрібно — пориньте в asipto devel-guide за implementation-деталями, які цей посібник навмисно резюмував.

---

<p align="center">
  <a href="./">← Зміст</a> · <a href="27-process-roles.md">← 9.1 Глосарій ролей</a>
</p>
