# 7.2 `kamcmd` — важіль оператора

> [!IMPORTANT]
> `kamcmd` — це тонкий BINRPC-клієнт через Unix-сокет — він *не знає* нічого спеціального про Kamailio. Здатність повністю походить з команд, зареєстрованих у живому інстансі. Але через те, що кожна важлива runtime-кнопка і кожен observability-хук йде через цей registry, `kamcmd` на практиці — **тул** для операцій над Kamailio.

## Що це насправді

`kamcmd` — це ~1 000 рядків C. Відкриває Unix-сокет, серіалізує method-and-arguments у BINRPC, читає BINRPC-response, гарно друкує. Це вся програма. Інтелект — список доступних команд, які приймають аргументи, який стан експонують — живе по інший бік сокета, зареєстрований у Kamailio'ому RPC-registry кожним завантаженим модулем.

Типовий виклик:

```bash
kamcmd <метод> [arg1] [arg2] …
```

Target за дефолтом — `/var/run/kamailio/kamailio_ctl` (або `/run/kamailio/kamailio_ctl`). `-s <path>` оверайдить. Жодного auth, жодного конфігу — лише шлях сокета.

## П'ять команд, що ви виконуватимете постійно

Якщо ви оперуєте Kamailio хоч скільки — ось у shell-history десятки разів:

```bash
# 1. Чи здоровий heap?
kamcmd core.shmmem
kamcmd core.pkgmem all

# 2. Скільки транзакцій / dialog'ів / контактів зараз?
kamcmd tm.stats
kamcmd dialog.stats_active
kamcmd ul.stats

# 3. Що саме в цій таблиці?
kamcmd htable.dump my_auth_cache
kamcmd dispatcher.list
kamcmd ul.dump

# 4. Що відбувається по кластеру?
kamcmd dmq.list_nodes

# 5. Перемкнути log-level наживо (без рестарту)
kamcmd dbg.set_level 3                  # увімкнути debug
kamcmd dbg.set_level 2                  # назад на info
```

Ці п'ять разом відповідають на більшу частину «чи Kamailio ок зараз?»-розслідувань. Пам'ять, in-flight-count'и, вміст таблиць, стан кластера, log-шум. Усе інше — варіації.

## Прихований gem: `rpc.entries` і `system.listMethods`

Коли не пам'ятаєте назву команди (а не пам'ятатимете, бо їх сотні) — рантайм каже:

```bash
kamcmd system.listMethods           # повний список currently-loaded RPC-методів
kamcmd rpc.entries                  # те ж, з одно-рядковими описами
kamcmd <prefix>.help                # module-specific help, де є
```

`system.listMethods` — авторитетна відповідь на «що я можу викликати на цьому Kamailio?» — бо відображає реальний завантажений set модулів, не лише docs. Не завантажений модуль тут команд не експонує.

## Читання виводу

Більшість команд повертає структуроване значення — мапу, масив, вкладену структуру. `kamcmd` рендерить як indented text. Наприклад, `tm.stats`:

```
{
  current: 0
  total: 18234
  current_size: 0
  rpl_received: 18229
  rpl_generated: 5
  rpl_sent: 18234
  …
}
```

Для machine-consumption `kamcmd -f '%v'` форматить одинокі значення — корисно для shell-скриптингу:

```bash
free_shm=$(kamcmd -f '%v' core.shmmem | grep ^free | awk '{print $2}')
```

Для багатшої структурованої видачі — JSON-RPC через HTTP. `kamcmd`-формат — human-first.

## Маніпуляція станом, обережно

Багато команд read-only — `stats`, `dump`, `list`. Але деякі — мутатори. Naming-патерни:

```bash
# set / delete entries
kamcmd htable.sets my_cache key123 "value"
kamcmd htable.delete my_cache key123

# помітити dispatcher-destination мертвим (чи назад живим)
kamcmd dispatcher.set_state ai 1 "sip:gw1:5060"   # ai = active inactive

# викинути dialog з кешу
kamcmd dlg.terminate_dlg <call-id> <from-tag>

# перезавантажити in-memory-таблиці модуля з БД
kamcmd dispatcher.reload
kamcmd permissions.addressReload
kamcmd htable.reload my_cache
```

> [!WARNING]
> Мутатори не ідемпотентні, не транзакційні. `htable.sets` зі stale-value переписує; `dispatcher.set_state` фліпає in-shm-flag миттєво без confirmation. Access-модель Unix-сокета припускає, що caller знає що робить.

## Чого `kamcmd` не може

Кілька речей дивують:

- **Не tail'ить логи.** Логи йдуть у syslog чи stdout, залежно від cfg; RPC — не log-канал. `journalctl -fu kamailio` чи що там у вас.
- **Не захоплює SIP-трафік.** Це територія tcpdump/sngrep. RPC бачить внутрішній стан Kamailio, не дріт.
- **Не може змінити семантику `kamailio.cfg`.** Routing запечений в AST на старті (розділ 2.4). RPC може лише фліпнути ті параметри модулів, що оголошені mutable.
- **Не говорить з мертвим Kamailio.** Сокет існує, лише поки main-процес живий. Після краху `kamcmd` каже «connection refused» — за дизайном.

## Чому такий дизайн хороший

`kamcmd` — мінімальний клієнт, бо RPC-шар Kamailio — справжній продукт. Перенесли команду в інший модуль, змінили формат виводу, додали нову — все прозоро для `kamcmd`. Тул написаний раз 10 років тому й рідко потребує змін. Усе цікаве — в коді модулів, експоноване через `rpc_export`.

Це й архітектура, що робить операції сталими: немає другої codebase для синхронізації, немає «kamcmd ще не підтримує нову фічу», немає «оновлю docs окремо». Що може running-сервер — те ви можете викликати.

Наступний розділ — друга половина operator-поверхні: event route'и, що дозволяють cfg реагувати на runtime-події так само, як на вхідні повідомлення.

---

<p align="center">
  <a href="./">← Зміст</a> · <a href="24-rpc-architecture.md">← 7.1 Архітектура RPC</a> · <a href="26-event-routes.md">Далі: 7.3 Event routes →</a>
</p>
