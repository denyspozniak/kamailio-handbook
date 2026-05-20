# 4. Движок скриптів — pointer-розділ

> [!IMPORTANT]
> Цей розділ навмисно тонкий. «Script engine» — як `kamailio.cfg` стає виконуваною поведінкою — вже покрите з двох боків: розділ 3.4 проходить routing-движок з боку *life-cycle повідомлення*, розділ 5.2 — з боку *KEMI-bridge*. Замість потрійного покриття одного й того ж — тут коротка карта що-де + кілька внутрішніх деталей, що не вписалися в ті розділи.

## Що де

| Тема | Покрита в |
|---|---|
| Які бувають route-блоки і коли стріляють | [3.4 Движок маршрутизації](10-routing-engine.md) |
| Дизайн-обмеження cfg DSL (без рекурсії, без колекцій) | [3.4](10-routing-engine.md) |
| Як `kamailio.cfg` стає in-memory AST | [3.4](10-routing-engine.md), [2.4 Lifecycle](05-lifecycle.md) |
| Чому зміни cfg потребують повного рестарту | [2.4](05-lifecycle.md) |
| Виклик функцій модулів з cfg | [3.4](10-routing-engine.md), [5.2 KEMI bridge](13-kemi-bridge.md) |
| Псевдо-змінні і lazy-парсинг | [3.2 Розпарсене повідомлення](08-parsed-message.md) |
| Lump-queuing як side-effect виконання скрипта | [3.3 Lumps](09-lumps.md) |
| Sub-route'и і як працює `route()` | [3.4](10-routing-engine.md) |
| Per-route-семантика `exit` / `drop` / `return 0` | [3.4](10-routing-engine.md) |
| Bridge cfg до KEMI-скриптів | [5.2 KEMI bridge](13-kemi-bridge.md) |

Якщо ви читали ті розділи — у вас є script engine. Решта цього розділу — деталі, що ніде не помістилися.

## Як route-блок насправді структурований у пам'яті

Після cfg-парсингу кожен route-блок — це масив `cfg_action_t`-структур. Кожна дія — одне з:

- Виклик функції (`t_relay()`, `record_route()` тощо) — тримає function-pointer і малий список аргументів.
- Control-flow-вузол (`if`, `else`, `switch`, `while`) — тримає child-action-список і condition.
- Assignment (`$var(x) = ...`) — тримає target-pseudo-variable-handler і вираз.
- Jump (`return`, `exit`, `drop`, `break`) — обробляється executor'ом прямо.

Executor — це маленький інтерпретатор (~кілька сотень рядків), що обходить це дерево в рантаймі. Це не VM у JIT-сенсі — жодного байткоду, жодної компіляції в native. Прямий AST-walk із function-pointer-disptch'ем.

Тому per-message script-overhead такий низький: немає «compile-once-then-execute»-непрямості. AST уже в оптимальній формі для інтерпретатора.

## Як `exit`, `drop` і `return 0` сигналізуються

Усі чотири script-level jump-ключові слова — `exit`, `drop`, `return`, `break` — компілюються в єдиний опкод (`DROP_T`) у executor'і. Різняться лише тим, який біт OR'ять у поле `run_flags` action-контексту: `EXIT_R_F`, `DROP_R_F`, `RETURN_R_F`, `BREAK_R_F` відповідно. `return 0` авто-промотується до додаткового `EXIT_R_F`. Головний loop executor'а (`run_actions` у `src/core/action.c`) читає лише `EXIT_R_F`/`RETURN_R_F`/`BREAK_R_F`, щоб вирішити, чи продовжувати walk-дерева — `DROP_R_F` executor не читає взагалі.

Для чого `DROP_R_F`: це сигнал **для caller'а `run_top_route`**. Routing-движок — той шматок core чи `tm`, що викликав route-блок — отримує назад `run_act_ctx`, який передав, інспектує `ctx.run_flags & DROP_R_F` і вирішує, чи пропустити свою default-continuation (форвардити reply, відправити branch, поширити failure тощо). Саме тому `drop` має різні ефекти в різних route'ах: кожен caller перевіряє біт у власній точці прийняття рішення. Per-route-таблиця — у [3.4](10-routing-engine.md).

Наслідок: route'и, викликані з `NULL` ctx — у першу чергу `failure_route` і `event_route[tm:branch-failure]` — не мають callable-місця, куди прийде біт. Скрипт усе ще може виконати `drop`, але прапор ніхто не читає. Подавлення у таких route'ах — через явні side-effect-виклики (`t_reply()`, `t_drop_replies()`, `append_branch` + `t_relay()`), зроблені до повернення зі скрипта.

## Псевдо-змінні як таблиця диспетчеризації

Кожен `$xxx` у cfg — це зареєстрований pseudo-variable-handler. Реєстрація структурно ідентична RPC- і KEMI-експортам:

```c
static pv_export_t mod_pvs[] = {
    {{"hdr", sizeof("hdr")-1}, PVT_HDR, pv_get_hdr, NULL, pv_parse_hdr_name, NULL, 0, 0},
    {{"ru",  sizeof("ru")-1},  PVT_RURI, pv_get_ruri, pv_set_ruri, NULL, NULL, 0, 0},
    /* … */
};
```

Кожен запис: ім'я, тип, getter, опційний setter, опційний name-parser. На стадії парсингу cfg-парсер шукає `$hdr` у зареєстрованих handler'ах і binду'ить скрипт до правильного function-pointer'а. У рантаймі обчислення `$hdr(X)` — це прямий виклик `pv_get_hdr` з параметром `X` — без name-lookup'у.

Тому псевдо-змінні дешеві, і тому деякі модулі можуть додавати нові (`$dlg_var`, `$shv`, `$avp`): реєстрація handler'ів відкрита. cfg DSL не має «системи типів» для змінних; кожен `$xxx` — те, чим оголосив його модуль, що зареєстрував.

## Трюк `if (function(...))`

Патерн, що з'являється постійно в `kamailio.cfg`:

```kamailio
if (is_method("INVITE")) {
    record_route();
}

if (!t_relay()) {
    sl_send_reply("503", "Internal error");
}
```

Це працює, бо **функції модулів повертають tri-state int**, який cfg інтерпретує як truthy/falsy:

- Позитивне (зазвичай `1`) → true, продовжуємо.
- Негативне → false, condition false.
- Нуль (рідко) → дропнути повідомлення цілком.

Це «конвенція», запечена в C-API. Автори модулів мають її дотримуватися, щоб функція була usable в `if (...)`. Майже всі функції модулів дотримуються.

`!` інвертує: `!t_relay()` — true, коли `t_relay()` повернув non-positive. `&&` і `||` — нормальні short-circuit. Conditions комбінуються дужками.

## Чому DSL не росте

Можна спитати, чому ніхто не додав loop'и по колекціях, справжні строки, словники в cfg DSL. Причини, приблизно в порядку:

1. **Це інвалідизувало б cheap-execution-модель.** foreach по динамічній колекції потребує per-iteration-алокації, name-resolution, GC. DSL швидкий, бо нічого цього немає.
2. **KEMI вже це розв'язує.** Усе, для чого ви б хотіли «справжню мову», робиться в Lua/Python/JS/Ruby через KEMI. Додати це в cfg — продублювати KEMI без його переваг.
3. **Backwards-compatibility.** DSL приблизно тієї ж форми з 2001-го. Додавання нових синтаксичних категорій ризикує parser-ambiguity з існуючими конфігами.

Як наслідок — навмисний розкол: cfg DSL для hot-path з простою формою; KEMI для всього іншого. Кордон працює саме тому, що його enforce'ить cfg DSL-навмисний мінімалізм.

## Коли реально читати цей розділ

Якщо ви певний час пишете route'и в Kamailio і «чому мій конфіг робить X» — debugging-питання, відповідь майже ніколи не тут — у 3.4 чи 5.2. Цей розділ для моменту, коли ви питаєте «*як* скрипт насправді працює», не «що мій скрипт має робити».

---

<p markdown="1" align="center">
  [← Зміст](../) · [← 9.2 Карта термінів](28-term-map.md)
</p>
