# 9.1 Глосарій ролей процесів

Швидка довідка — що насправді означає кожен процес у живому Kamailio, у порядку, в якому ви побачите їх через `ps -ef | grep kamailio`.

| Процес | Кількість | Роль | Чіпає SIP? | Деталі |
|---|---|---|---|---|
| **main** | 1 | Батько всіх інших процесів. Реапить мертвих, поширює сигнали. | Ні | Спавниться, коли стартує `kamailio`; PID == той, що в `/var/run/kamailio.pid`. |
| **attendant** | 1 | Допоміжний супервайзер для частини lifecycle-сигналів. | Ні | Legacy з SER-родоводу. Переважно можна не зважати. |
| **udp receiver** | `children` per UDP-listener (дефолт 8) | Основна маса SIP-traffic-handler'ів. Loop'ить на `recvfrom()`. | Так | Тут біжить `request_route` для UDP. Один воркер на пакет, від початку до кінця. |
| **tcp main** | 1 | `accept()`'ить нові TCP/TLS-з'єднання, роздає FD'и TCP-воркерам. | Ні (control-plane) | Відділяє accept від message-processing. |
| **tcp worker** | `tcp_children` (дефолт 4) | Читає SIP-стрими зі своїх TCP-з'єднань, fram'ить повідомлення, дзвонить `receive_msg()`. | Так | Тут біжить `request_route` для TCP, TLS, WebSocket. |
| **timer** | 1 | Стріляє швидкі (~100 мс tick) таймери: tm retransmission'и, dialog keepalive, dispatcher probing. | Так (може емітити SIP) | Драйвить timer wheels з розділу 6.1. |
| **slow timer** | 1 | Стріляє повільні таймери: wait timer у tm, cleanup-задачі. | Ні | Виділений від fast timer, щоб housekeeping не з'їдав retransmission'и. |
| **ctl** | 1 | Слухає BINRPC Unix-сокет. | Ні | З ним говорить `kamcmd`. |
| **jsonrpcs** | 1 (коли завантажений) | Слухає JSON-RPC через HTTP/FIFO/UDP. | Ні (control plane) | HTTP-based RPC-сервер. |
| **dialog (keepalive)** | 1 (з KA) | Шле OPTIONS-пінги confirmed-діалогам. | Так | Виявляє partition-induced dead calls. |
| **htable (expiry)** | 1 (коли завантажений) | Періодично свіпає expired entries htable. | Ні | Один sweep по всіх htable. |
| **dispatcher (probing)** | 1 (з probing'ом) | OPTIONS-ить dispatcher-destination'и, мітить мертвих/живих. | Так | Liveness-детектор gateway'ів. |
| **dmq (worker)** | 1+ (коли завантажений) | Обробляє вхідні DMQ-повідомлення від peer-інстансів. | Ні | Replication-транспорт. |
| **usrloc (expiry)** | 1 (коли завантажений) | Свіпає expired contacts; flush'ить dirty в БД. | Ні | Патерн usrloc з розділу 6.3. |
| **app_lua / app_python helpers** | різно | Per-language reload-координатори, якщо є. | Ні | У кожному воркері свій інтерпретатор; ці helper'и роблять bookkeeping. |
| **xhttp_prom / xhttp_pi / …** | по 1 кожного | HTTP-based management-інтерфейси, коли завантажені. | Ні | Кожен відкриває свій listener усередині Kamailio. |

Кількість видимих процесів залежить від набору завантажених модулів. Мінімальний конфіг з `tm` і `sl` — десь дюжина. Продакшн з dialog, dispatcher, dmq, usrloc, htable, KEMI, HTTP-інтерфейсами — спокійно 25–40.

## Як ідентифікувати зовні

Процеси самі ставлять собі ім'я через `prctl(PR_SET_NAME)`, тож `ps` показує читабельні описи:

```
kamailio: main process
kamailio: udp receiver child=3 udp:10.0.0.1:5060
kamailio: tcp main process
kamailio: tcp receiver (1) child=2
kamailio: timer
kamailio: slow timer
kamailio: ctl handler
kamailio: jsonrpcs http handler
kamailio: Dialog KA Timer
kamailio: HTable Expire Timer
kamailio: Dispatcher Probing
kamailio: DMQ Worker [0]
…
```

Формат — `kamailio: <роль> [<index>]` для indexed-воркерів. `rank` з розділу 2.1 — це той самий index, використовується внутрішньо для seed'у RNG і вибору timer-слотів.

## Що рестартиться на крах воркера

| Тип процесу | Якщо помер… |
|---|---|
| UDP/TCP/timer-воркери | Main одразу пере-форкає |
| TCP main | Main пере-форкає; існуючі TCP-з'єднання втрачаються |
| Module helpers (dialog KA, htable expire, dispatcher probe, dmq тощо) | **Зазвичай не рестартиться.** Module-specific. |
| ctl / jsonrpcs | Main пере-форкає |
| Main сам | Увесь Kamailio термінується |

> [!WARNING]
> Module-helper, що помер і не рестартиться (наприклад, dispatcher probing) тихо деградує сервіс — gateway'и перестають пінгуватися, мертві destination'и не мітяться, виклики йдуть в нікуди. Алертіть на rate `SIGCHLD`, не лише на aliveness main-процесу.

---

<p markdown="1" align="center">
  [← Зміст](../) · [← 7.3 Event routes](26-event-routes.md) · [Далі: 9.2 Карта термінів →](28-term-map.md)
</p>
