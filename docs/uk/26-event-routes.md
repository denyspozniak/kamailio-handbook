# 7.3 Event route'и — runtime-хуки

> [!IMPORTANT]
> Більшість route-блоків у Kamailio стріляють тому, що прилетіло SIP-повідомлення (`request_route`, `onreply_route`), або тому, що `tm` щось вирішив про транзакцію (`branch_route`, `failure_route`). **Event route'и** стріляють через *щось інше* — стартував воркер, peer впав, HTTP-запит влетів у listener, таймер expired, скрипт reload'нувся. Це програмована hook-поверхня самого рантайму.

## Як виглядають

Event route — це просто іменований route-блок з module-and-event-префіксом:

```kamailio
event_route[tm:branch-failure] {
    xlog("L_INFO", "branch failed for $T(reply_code) $T(reply_reason)\n");
}

event_route[dispatcher:dst-down] {
    xlog("L_WARN", "gateway $rd just went DOWN\n");
}

event_route[htable:expired:auth_cache] {
    xlog("L_DBG", "auth cache entry expired: $shtex(key)\n");
}
```

Коли рантайм виявляє одну з цих подій — диспетчеризує іменований route рівно як `request_route` — той самий pre-compiled AST, та сама поверхня функцій модулів, ті самі псевдо-змінні (з поправкою на доступне в контексті). Різниця — в тригері.

## Категорії подій

Різні модулі експонують різні події. Well-known:

| Event | Коли стріляє | Що доступно |
|---|---|---|
| `event_route[tm:branch-failure]` | Конкретний branch отримав non-2xx final | `$T(...)` для transaction-info |
| `event_route[tm:local-response]` | tm побудував reply (timeout тощо) | Reply, що конструюється |
| `event_route[xhttp:request]` | HTTP-запит влетів у Kamailio-сокет | `$hu`, `$rb` для URL і body |
| `event_route[xhttp_pi:request]` | Те ж для management-interface | — |
| `event_route[dispatcher:dst-down]` | Destination щойно помічений мертвим | `$rd` для destination URI |
| `event_route[dispatcher:dst-up]` | Destination повернувся | `$rd` |
| `event_route[htable:expired:<table>]` | Entry щойно expir'нувся і видалений | `$shtex(key)`, `$shtex(value)` |
| `event_route[htable:mod-init]` | Таблиця ініціалізована на старті | — |
| `event_route[dialog:start]` | Dialog перейшов з EARLY у CONFIRMED | `$dlg_var(...)` |
| `event_route[dialog:end]` | Dialog термінувався | `$dlg_var(...)` |
| `event_route[dmq:peer-down]` | dmq-peer перестав відповідати | URI peer'а |
| `event_route[sip:reply-lost]` | Reply не вдалося відіслати назад | — |
| `event_route[core:worker-pre-init]` | Безпосередньо перед стартом воркерів (у main) | — |

Naming-конвенція консистентна: `module:event-name` або `module:event-name:specific-arg`. Документація модуля перелічує, які події він піднімає.

## Навіщо вони

Три причини у порядку зростання користі:

**1. Side-effect'и без забруднення `request_route`.** Handler, що має стрельнути на dispatcher-state-change — оновити Prometheus-counter, пушнути webhook, лог у custom-файл — не належить у `request_route`. Він належить у event-route, що стріляє лише коли подія справді сталася.

**2. State machines.** Комбінація `event_route[dialog:start]` і `event_route[dialog:end]` дає місце для custom per-call counter'ів і таймерів, не вартих окремого модуля.

**3. Async-chaining.** Розділ 8.2 показав `t_continue()`, що жене виконання у resume-route. Цей resume-route — механічно — event-route: та сама диспетчеризація, та сама модель контексту. Будь-який зовнішній виклик з поверненням — destination — це event-route.

## Що інше в execution-контексті

Event route'и біжать **поза контекстом вхідного SIP-повідомлення** (переважно). Деякі псевдо-змінні, що працюють у `request_route`, у event-route — NULL чи undefined: `$ru`, `$tu`, `$si` можуть не мати сенсу, якщо подія не прив'язана до повідомлення. Читайте документацію модуля, що які поля для якої події заповнюються.

Завжди можна:
- Викликати більшість module-функцій (з поправкою на контекст — `t_relay()` не працює без транзакції).
- Лог через `xlog`.
- Чіпати htable і інший shared-state.
- Видавати RPC-події назад у систему (наприклад, нотифікувати dmq-peer'ів).
- Читати й писати `$shv()` і `$shtex()`.

Зазвичай не можна:
- Викликати `t_relay()` — немає оригінального повідомлення для relay'ю.
- Модифікувати lumps — немає `sip_msg`, до якого їх чіпляти.
- Покладатися на `$var(...)` — per-message-арена воркера може бути порожньою.

> [!TIP]
> Event route'и короткі за дизайном. Якщо handler більше 30 рядків — логіка ймовірно належить у скрипт (KEMI) чи модуль, не в cfg. Event route'и працюють найкраще як **dispatch-glue**: detect, log, інкремент counter'а, виклик sub-route'у чи скрипт-функції.

## Куди event route'и підключаються

Дві архітектурні частини, що ми вже покрили, явно використовують event route'и:

- **Async-транзакції** (розділ 8.2) — `t_continue()` входить в event-route-shaped resume.
- **KEMI** (розділ 5.2) — `event_route_callback("event:name", "ksr_handler")` дозволяє направити диспетчеризацію event-route'у в script-функцію замість cfg-блоку. Корисно, коли event-handling-логіка достатньо складна, щоб хотіти справжньої мови.

Те, що все це ділиться однією машинерією — навмисно: в Kamailio лише один event-dispatch-механізм, перевикористовуваний скрізь, де щось має стріляти поза нормальною SIP-обробкою.

## Маленький worked-example

Поширений operational-патерн: коли dispatcher-destination падає, лог у custom-дашборд і нотифікувати dmq-peer'ів, щоб усі помітили той самий destination мертвим.

```kamailio
event_route[dispatcher:dst-down] {
    xlog("L_ALERT", "DISPATCHER_DOWN $rd\n");
    
    # post у internal-дашборд через HTTP
    $var(body) = "{\"event\":\"dst-down\",\"dst\":\"$rd\"}";
    http_async_query("http://dashboard.internal/sip-events", "dashboard_done");
    
    # дати знати іншим Kamailio-нодам
    $sht(degraded=>$rd) = 1;
    # dmq реплікує htable-зміну
}

event_route[dashboard_done] {
    if ($http_rs != 200) {
        xlog("L_WARN", "dashboard rejected event: $http_rs\n");
    }
}
```

Три event-route'и в одному ланцюгу: реальний `dispatcher:dst-down`, `dashboard_done`-resume для async-HTTP, і (імпліцитно) dmq-реплікація htable-зміни, що стріляє свої handler'и на peer-нодах.

Наступний розділ закриває посібник коротким reference'ом: глосарієм ролей процесів і картою термінів.

---

<p markdown="1" align="center">
  [← Зміст](../) · [← 7.2 kamcmd](25-kamcmd.md) · [Далі: 9.1 Ролі процесів →](27-process-roles.md)
</p>
