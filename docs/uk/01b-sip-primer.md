# 1.2 SIP за 60 секунд

> [!IMPORTANT]
> Посібник передбачає, що SIP на протокольному рівні ви знаєте. Якщо це було давно — ця сторінка дає мінімальну лексику, щоб слідувати за архітектурними розділами. RFC 3261 — канонічне джерело; нижче — погляд оператора.

## Транзакції

**Транзакція** — це один SIP-запит плюс усе, що на нього відповідає: provisional-відповіді, retransmission'и, і рівно одна final-відповідь. Двi state machine:

- **INVITE-транзакція** — три-стороння: `INVITE → (1xx)* → 2xx-or-failure → ACK`. ACK закриває.
- **Non-INVITE-транзакція** — двостороння: `REQUEST → (1xx)* → final response`. Жодного transaction-level ACK.

Ідентифікується через `Via:branch + From:tag + Call-ID + CSeq`. Transaction-layer у Kamailio (`tm`, розділ 6.1) трекає кожну in-flight-транзакцію у shm.

## Діалоги

**Діалог** — це довгоживуче peer-співвідношення між двома UA, встановлене через `INVITE`/2xx/ACK і завершене через `BYE`. Кілька транзакцій біжать всередині одного діалогу: setup-INVITE, mid-dialog re-INVITE (hold/resume, SDP-renegotiation), UPDATE, REFER, BYE.

Ідентифікується через `Call-ID + From-tag + To-tag` — та сама трійка на кожному in-dialog-повідомленні. Dialog-layer у Kamailio (`dialog`, розділ 6.2) сидить поверх `tm` і склеює транзакції в один виклик.

## ACK — найхитріше повідомлення у SIP

ACK має **дві різні семантики** залежно від того, що він підтверджує. Це найбільше дивує новачків у SIP.

| Підтверджена відповідь | ACK називається | Hop-scope | Нова транзакція? |
|---|---|---|---|
| 2xx (успіх) | **positive ACK** | End-to-end (UAC → UAS, **не** проксіюється на tx-рівні) | **Так — власна нова транзакція** |
| 3xx–6xx (failure) | **negative ACK** | Hop-by-hop (всередині INVITE-транзакції) | **Ні — частина INVITE-транзакції** |

Операційні наслідки для проксі:

- **Positive ACK** оминає transaction-layer повністю. Проксі, що хоче його бачити, мусить зробити `record_route()` на INVITE — щоб dialog'овий route-set тримав проксі на in-dialog-шляху; інакше ACK іде UAC→UAS напряму.
- **Negative ACK** з'їдається локально через `tm` як закриваюча грань INVITE-транзакції — це механізм, щоб транзакція чисто закінчилася без retransmission-storm'ів.

Забути цю різницю — типовий спосіб «загубити» 2xx-ACK і зламати in-dialog-routing.

## Роль проксі

SIP-**проксі** — це форвардер: отримує запити, приймає routing-рішення, шле далі. RFC 3261 розрізняє:

- **Stateless proxy** — отримав, вирішив, переслав. Жодного стану, жодного retransmission-handling'у. Дешевий і швидкий, але не може форкати чи відновлюватися від failed-branch.
- **Stateful proxy** — створює транзакцію per forwarded request. Трекає branch'і, handle'ить retransmission, може форкати, бігти `failure_route`, перехоплювати reply'ї. Майже всі продакшн-розгортання.

Що проксі **не робить** (це і є межа між проксі і **B2BUA**):

- Не започатковує діалоги сам по собі.
- Не термінує діалоги, видаючи власний BYE.
- Не переписує `Call-ID`, tag'и чи інші dialog-ідентифікатори.
- Не генерує reply'ї від імені UAS (вузькі винятки на кшталт `100 Trying`).

Kamailio — це проксі. Out of the box тримається проксі-контракту. Модулі типу `uac` і `topos` розмивають межу, коли налаштовані — і знати, що ви її перетнули, ваша справа.

## Де ці концепти спливають у посібнику

| Концепт | Де |
|---|---|
| Transaction-стан у shm | [6.1 Транзакції (`tm`)](16-tm-internals.md) |
| Retransmission-таймери і timer wheels | [6.1](16-tm-internals.md) |
| Dialog state machine | [6.2 Діалоги](17-dialogs.md) |
| Матчинг reply'ю до транзакції | [3.5 Форвардинг і відповіді](11-forwarding.md) |
| Stateless vs stateful-форвард | [3.5](11-forwarding.md), [2.5 Sizing](06-sizing-and-tuning.md) |
| Форк / branch'і | [3.5](11-forwarding.md) |
| Межа proxy-vs-B2BUA | [8.1 Topology hiding](19-topos.md), цей розділ |

---

<p markdown="1" align="center">
  [← Зміст](../) · [← 1.1 Вступ](01-introduction.md) · [Далі: 2.1 Процесна модель →](02-process-model.md)
</p>
