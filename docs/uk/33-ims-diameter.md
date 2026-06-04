# 10.3 Сторона Diameter

> [!IMPORTANT]
> SIP несе виклик. **Diameter** несе все, від чого виклик *залежить* — хто абонент, чи йому можна, який QoS отримає його медіа і скільки це коштує. CSCF, який не вміє в Diameter — це proxy, що нікого не зареєструє і нічого не авторизує. Тож поряд зі своїм SIP-стеком Kamailio крутить повноцінний Diameter-peer — і розуміння цього peer'а є половиною розуміння Kamailio-в-IMS.

## Навіщо IMS другий протокол узагалі

SIP — session-протокол; йому не діло знати ваш тариф, ваші auth-вектори чи ваш prepaid-баланс. 3GPP поклали все це на **Diameter** (RFC 6733) — AAA-протокол із request/answer-моделлю команд, структурованими **AVP** (Attribute-Value Pairs) і персистентними peer-з'єднаннями. Кожен Diameter-лінк в IMS — це один із reference-points з [10.1](31-ims-overview.md): Cx до HSS, Rx до PCRF, Ro/Rf до системи білінгу.

## `cdp` — C Diameter Peer

Diameter-стек Kamailio — це модуль **`cdp`** (C Diameter Peer), з `cdp_avp` для типізованих хелперів читання/побудови AVP. `cdp` завантажується один раз і **шариться** всіма IMS-модулями, яким потрібен Diameter — `ims_icscf`, `ims_registrar_scscf`, `ims_auth`, `ims_qos`, `ims_charging` усі звертаються до нього, а не відкривають кожен своє з'єднання.

Ключові властивості:

- **Персистентні peer'и.** `cdp` тримає довгоживучі з'єднання до кожного Diameter-peer'а (HSS, PCRF, OCS чи DRA перед ними) зі своїм connection state machine: робить Capabilities-Exchange (CER/CEA) на конекті і Device-Watchdog (DWR/DWA) keepalive'и для виявлення мертвих peer'ів.
- **Конфіг в XML.** На відміну від більшості конфіга Kamailio, `cdp` налаштовується зовнішнім XML-файлом (realm, список peer'ів, транспорт, AVP-словники), на який посилається cfg. Це спадок OpenIMSCore.
- **Async за природою.** Diameter round-trip стається *усередині* SIP-обробки — S-CSCF не може відповісти на REGISTER, поки не повернеться MAA. IMS-модулі використовують async/transaction-suspend-машинерію Kamailio (див. [8.2 Async-транзакції](20-async-transactions.md)), щоб воркер не блокувався на дроті, чекаючи HSS.

## Що Kamailio говорить, і на якому модулі

| Інтерфейс | Бік Kamailio | Peer | Що робить |
|---|---|---|---|
| **Cx** | `ims_icscf`, `ims_registrar_scscf`, `ims_auth` | HSS | Auth, вибір S-CSCF, завантаження профілю/iFC |
| **Rx** | `ims_qos` | PCRF / PCF | Авторизувати медіа, запросити виділений bearer із QoS |
| **Ro** (online) / **Rf** (offline) | `ims_charging` | OCS / CHF | Credit control: зарезервувати юніти, списати, звільнити |

### Command code'и, які вам трапляться

Cx (HSS):

| Code | Команда | Тригер |
|---|---|---|
| 300 | **UAR**/UAA — User-Authorization | I-CSCF на REGISTER |
| 303 | **MAR**/MAA — Multimedia-Auth | S-CSCF тягне auth-вектор |
| 301 | **SAR**/SAA — Server-Assignment | S-CSCF реєструє себе + тягне iFC |
| 302 | **LIR**/LIA — Location-Info | I-CSCF на термінуючому виклику |
| 304 | **RTR**/RTA — Registration-Termination | HSS пушить дереєстрацію в S-CSCF |
| 305 | **PPR**/PPA — Push-Profile | HSS пушить оновлення профілю |

Rx (PCRF), Ro (OCS):

| Code | Команда | Тригер |
|---|---|---|
| 265 | **AAR**/AAA — AA-Request | P-CSCF авторизує медіа сесії |
| 275 | **STR**/STA — Session-Termination | P-CSCF зносить авторизацію медіа |
| 274 | **ASR**/ASA — Abort-Session | PCRF аборти сесію |
| 272 | **CCR**/CCA — Credit-Control | S-CSCF резервує/списує charging-юніти |

> [!NOTE]
> Коли мережа multi-home'ить HSS, I/S-CSCF спершу питає **SLF** (Subscription Locator Function), який HSS тримає даного користувача — SLF відповідає Diameter-Redirect'ом (reference-point **Dx**). На практиці цю роботу дедалі частіше віддають **DRA** (Diameter Routing Agent), що проксює Cx до правильного HSS; CSCF просто наводить `cdp` на DRA. Більше про DRA — у [10.4](34-ims-full-solution.md).

## Що вас вбиває

- **Peer flapping.** Якщо з'єднання до HSS/DRA падає, `cdp` зносить його і ретраїть — і в це вікно кожен REGISTER провалюється (немає MAA). Стежте за CER/DWR-станом; peer, що мовчить на watchdog'ах, ось-ось забере ваші реєстрації з собою.
- **Розбіжність AVP-словників.** `cdp` розуміє лише ті AVP, що в завантажених словниках. Peer (HSS/PCRF), що шле vendor-specific-AVP, якого `cdp` не знає, отримує цей AVP дропнутим або повідомлення відхиленим — а збій виринає як заплутана SIP-side-помилка далеко від справжньої причини.
- **Блокування воркера.** Якщо async-обв'язка неправильна і модуль робить *синхронний* Diameter-виклик, одна повільна відповідь HSS паркує SIP-воркера на весь таймаут. На registration storms це каскадить швидко. Уся суть suspend/continue-машинерії — уникнути саме цього.

---

<p markdown="1" align="center">
  [← Зміст](../) · [← 10.2 Ролі CSCF](32-ims-cscf.md) · [Далі: 10.4 Повне рішення →](34-ims-full-solution.md)
</p>
