<p align="center">
  <img src="assets/banner.svg" alt="CodeCheck MCP" width="100%">
</p>

<h1 align="center">CodeCheck MCP</h1>

<p align="center">
  <a href="#установка">Установка</a> ·
  <a href="#цикл-build--audit--fix--re-audit">Цикл исправлений</a> ·
  <a href="#инструменты">Инструменты</a> ·
  <a href="llms-install.md">Для ИИ-агентов</a> ·
  <a href="CONTRIBUTING.md">Участие</a> ·
  <a href="SECURITY.md">Безопасность</a>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-2ea44f" alt="Лицензия: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-3776ab" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/MCP-server-8a2be2" alt="MCP-сервер">
  <a href="README.md"><img src="https://img.shields.io/badge/lang-English-0d9488" alt="English"></a>
  <a href="README.ru.md"><img src="https://img.shields.io/badge/lang-%D0%A0%D1%83%D1%81%D1%81%D0%BA%D0%B8%D0%B9-d64545" alt="Русский"></a>
</p>

MCP-сервер, который **проверяет готовый веб-проект в настоящем браузере** и пишет отчёт, по которому другой ИИ
может исправить код. Он открывает сайт через Playwright, обходит страницы, жмёт кнопки, следит за консолью и сетью,
меряет вёрстку на нескольких ширинах экрана, запускает axe-core для доступности, проверяет SEO, картинки, шрифты,
скорость и базовую безопасность. У каждой проблемы есть постоянный ID, CSS-селектор, доказательства и скриншот.

Запустите проверку ещё раз после правок, и она скажет, что исправлено, что появилось нового и что осталось.

Проверялось на Windows и Python 3.14. Другие ОС и версии Python не проверялись.

| | |
|---|---|
| **Настоящий браузер** | Chromium через Playwright: реальные клики, реальная вёрстка, реальная сеть. Ничего не угадывается по исходному коду. |
| **Сделан для цикла исправлений** | `current.json`: одна запись на проблему, с правилом, страницей, селектором или URL, доказательствами и отпечатком, который не меняется между прогонами. |
| **Доказательства, а не мнения** | В каждой находке написано, что именно измерено. У critical и warning есть скриншот, элемент обведён красным. |
| **Приоритеты** | Находки собираются в группы по причине: первопричина, связанные с ней проблемы, страницы, влияние 1-10 и что исправить. Выведенные связи помечены как предполагаемые. |
| **Сравнение прогонов** | Каждый прогон сравнивается с предыдущим: ✅ исправлено, 🔴 новое, ⚠️ без изменений. |
| **Безопасен по устройству** | Проект только читается, браузер изолирован, переходы на чужие домены блокируются, проверки безопасности только пассивные. |

## Установка

Нужны Python 3.10+ и интернет (Chromium весит около 150 МБ).

```bash
# 1. Создайте окружение и установите пакет прямо из GitHub
python -m venv codecheck-env
codecheck-env/Scripts/pip install git+https://github.com/aleks-fw/CodeCheck-MCP.git      # Windows
# codecheck-env/bin/pip install git+https://github.com/aleks-fw/CodeCheck-MCP.git        # macOS / Linux

# 2. Один раз скачайте браузер для Playwright
codecheck-env/Scripts/python -m playwright install chromium
```

### Подключение к Claude Code

```bash
claude mcp add --scope user codecheck -- "<путь>/codecheck-env/Scripts/codecheck-mcp"
```

### Подключение к другим клиентам (Claude Desktop, Cursor и т. п.)

```json
{
  "mcpServers": {
    "codecheck": {
      "command": "<путь>/codecheck-env/Scripts/codecheck-mcp",
      "env": { "CODECHECK_REPORTS_DIR": "<куда класть отчёты>" }
    }
  }
}
```

`<путь>` — абсолютный путь к папке, где вы создали окружение. `CODECHECK_REPORTS_DIR` необязателен (по умолчанию
`~/codecheck-reports`). Перезапустите клиент, и в списке MCP появится `codecheck`.

### Если вы ИИ-агент

Установите по инструкции из [llms-install.md](llms-install.md).

## Цикл Build → Audit → Fix → Re-audit

1. **Build.** Соберите сайт или запустите его локально.
2. **Audit.** Скажите агенту: *«Запусти audit_project на http://localhost:5173 с criticalSelectors ["#checkout"]»*.
   В ответе будут счётчики по серьёзности, список critical, первые группы Prioritized Issues и пути к
   `report.md` и `current.json`.
3. **Fix.** *«Прочитай current.json и исправь critical и warning. Код ищи по selector, url и evidence каждой
   находки»*. В каждой находке указаны правило, страница, элемент или ресурс и то, что наблюдалось, поэтому
   агенту не нужно сначала воспроизводить ошибку.
4. **Re-audit.** Запустите `audit_project` ещё раз с тем же `url`. Ответ начнётся со строки
   `Since the previous run: ✅ Fixed 3 · 🔴 New 0 · ⚠️ Unchanged 12`; повторяйте, пока не уйдут все critical.

Находка считается исправленной, только если новый прогон проверил ту же категорию, страницу и ширину экрана.
Иначе она попадает в «not rechecked», поэтому более узкий прогон не покажет ложных исправлений.

## Инструменты

| Инструмент | Параметры | Что делает |
|---|---|---|
| `audit_project` | `url`, `maxPages=10`, `viewports=[375, 768, 1280]`, `checks=все`, `criticalSelectors=[]`, `outputDir` | Полный аудит для цикла исправлений, см. ниже |
| `compare_reports` | `previous`, `current` (пути к JSON-отчётам) | Fixed / New / Unchanged между любыми двумя отчётами `audit_project` |
| `full_qa` | `target`, `max_pages=10` | Быстрый QA всеми проверками ниже, отчёт на русском |
| `test_interactions` | `target`, `max_pages` | Мёртвые кнопки, отключённые, что всё равно реагируют, перекрытые кнопки, формы, двойная отправка, битые якоря |
| `test_layout` | `target`, `max_pages`, `widths=[320, 375, 768, 1024, 1440]` | Наложение и обрезка текста, горизонтальный скролл, контраст (в том числе на картинках), зоны нажатия меньше 44 px |
| `test_fonts` | `target`, `max_pages` | Семейства шрифтов, шрифты-«чужаки», незагрузившиеся веб-шрифты, разброс размеров, иерархия заголовков |
| `test_images` | `target`, `max_pages` | Битые, растянутые, «мыльные», тяжёлые картинки, нет `alt` |
| `quick_security` | `target`, `max_pages=3` | Секреты в файлах и истории git, `.env` в git, заголовки, cookies, mixed content |

`url` / `target` — это URL или путь к папке или файлу проекта; для папки поднимается временный локальный сервер.

### audit_project

| Параметр | По умолчанию | Что значит |
|---|---|---|
| `url` | обязателен | URL сайта или папка / файл проекта |
| `maxPages` | `10` | Сколько страниц обойти, только в пределах того же origin |
| `viewports` | `[375, 768, 1280]` | Ширины экрана в px (высоты 812, 1024, 800) |
| `checks` | все | Любые из `interaction`, `layout`, `images`, `fonts`, `console`, `accessibility`, `seo`, `performance`, `security`, `network` |
| `criticalSelectors` | `[]` | Селекторы ключевых действий (например, `#checkout`); если такой элемент не реагирует на клик, находка critical |
| `outputDir` | `<CODECHECK_REPORTS_DIR>/<проект>` | Куда писать `current.json`, `previous.json`, `report.md` и `screenshots/` |

Пример вызова:

```json
{
  "url": "http://127.0.0.1:8765/",
  "criticalSelectors": ["#checkout"],
  "viewports": [375, 768, 1280]
}
```

Ответ (настоящий прогон на [examples/demo-shop](examples/demo-shop) с `criticalSelectors: ["#checkout",
"#place-order"]`, второй запуск после того, как добавили недостающий `<title>`):

```text
CodeCheck audit of http://127.0.0.1:8765/: 9 page(s), viewports 375x812, 768x1024, 1280x800.
Critical: 8 · Warnings: 5 · Notices: 31

Critical:
- CC-001 `interaction/no-effect` on /buttons.html: Clicking #checkout does nothing
- CC-002 `interaction/action-request-failed` on /cart.html: Clicking #place-order sends POST /api/order, which answers HTTP 500
- CC-003 `interaction/action-request-failed` on /checkout.html: Clicking #place-order sends POST /api/order, which answers HTTP 500
- CC-004 `console/uncaught-exception` on /errors.html: Uncaught exception: ReferenceError: cartItems is not defined
- CC-005 `accessibility/image-alt` on /media.html: Images must have alternative text
- CC-006 `network/api-5xx` on /api.html: API request returned HTTP 500
- CC-007 `network/api-5xx` on /checkout.html: API request returned HTTP 500
- CC-008 `network/script-failed` on /media.html: JavaScript file did not load

Top issues (5 of 17 groups):
- G-01 🔴 CRITICAL · impact 10/10 · API request returned HTTP 500 (/api/order) · pages: /cart.html, /checkout.html · 3 related
- G-02 🔴 CRITICAL · impact 10/10 · Clicking #checkout does nothing · pages: /buttons.html
- G-03 🔴 CRITICAL · impact 9/10 · Uncaught exception: ReferenceError: cartItems is not defined · pages: /errors.html
- G-04 🔴 CRITICAL · impact 9/10 · API request returned HTTP 500 (/api/orders) · pages: /api.html
- G-05 🔴 CRITICAL · impact 9/10 · JavaScript file did not load (/js/missing.js) · pages: /media.html

Since the previous run: ✅ Fixed 1 · 🔴 New 0 · ⚠️ Unchanged 44
Fixed:
  CC-013 `seo/missing-title` on `/notitle.html`: Page has no title

Report: .../report.md
JSON: .../current.json
Screenshots: .../screenshots
```

Первая группа из того же `report.md` (отчёт на английском: его читает прежде всего ИИ):

```markdown
## Prioritized Issues

### 🔴 CRITICAL — API request returned HTTP 500 (/api/order)

- **Impact:** 10/10 (severity 8, breaks a function or exposes data +1, on several pages +1,
  key action (criticalSelectors) +1, causes other issues +1)
- **Category:** functionality
- **Affected pages:** `/cart.html`, `/checkout.html`
- **Root cause:** GET http://127.0.0.1:8765/api/order answered HTTP 500 on /checkout.html. (CC-007)
- **Related issues:**
  - CC-002 `interaction/action-request-failed` on `/cart.html`: Clicking #place-order sends POST /api/order,
    which answers HTTP 500 (confirmed: the click sends a request to the same failing endpoint /api/order)
  - CC-003 `interaction/action-request-failed` on `/checkout.html`: Clicking #place-order sends POST /api/order,
    which answers HTTP 500 (confirmed: the click sends a request to the same failing endpoint /api/order)
  - CC-010 `console/error` on `/checkout.html`: console.error: Could not load the order summary: GET /api/order
    returned 500 (confirmed: the error text mentions /api/order)
- **Recommendation:** The API endpoint in evidence fails on the server: check its server logs, fix the handler,
  and make the page show an error state when the request fails.
- **Evidence:** screenshots: [screenshots/CC-002.png](screenshots/CC-002.png), ... · urls:
  `http://127.0.0.1:8765/api/order` · selectors: `#place-order` · requests:
  `POST http://127.0.0.1:8765/api/order → 500`, `GET http://127.0.0.1:8765/api/order → 500` · console:
  `Could not load the order summary: GET /api/order returned 500`
```

Ниже идут Summary, все находки по серьёзности и категориям (у каждой свой скриншот и доказательства), список проверенных страниц и по одной рекомендации на каждое встреченное правило.

### Prioritized Issues

После всех проверок находки собираются в группы, по одной на причину, и сортируются по серьёзности, затем по
влиянию, затем по числу затронутых страниц. Связи между находками берутся только из самих находок:

| Связь | Основание | Пометка |
|---|---|---|
| Одна и та же проблема на нескольких страницах | тот же URL ресурса, или то же правило и селектор, или тот же текст | одна группа |
| Упавший запрос и клик, который шлёт запрос на тот же адрес | тот же путь URL | confirmed |
| Упавший запрос и ошибка в консоли, где назван его URL | URL в тексте ошибки | confirmed |
| Тяжёлый файл и вес страницы | файл среди самых больших загрузок страницы | confirmed |
| Не загрузился скрипт, и на странице ошибки «is not defined» или мёртвые кнопки | та же страница | likely |
| Необработанное исключение и мёртвая кнопка на странице | та же страница | likely |
| Упавший запрос и ошибка в консоли про запрос, где URL не назван | та же страница | likely |
| Не загрузились стили и находки вёрстки; медленный запрос и медленная загрузка | та же страница | likely |

Если все связи группы подтверждены, в отчёте написано **Root cause**; если хотя бы одна выведена, —
**Likely root cause**. Ошибки консоли записываются при загрузке страницы, до кликов, поэтому с запросами от кликов
они не связываются никогда.

У каждой группы есть:

- **severity:** CRITICAL (есть critical), HIGH (warning про функциональность или безопасность), MEDIUM (другой
  warning), LOW (только notice);
- **category:** `functionality`, `responsive`, `performance`, `accessibility`, `security`, `visual` или `other`;
- **impact 1-10:** 8 / 5 / 2 за critical / warning / notice, +1 если ломает функцию или раскрывает данные, +1 на
  нескольких страницах или +2 на большинстве, +1 за ключевое действие из `criticalSelectors`, +1 если из-за неё
  есть 2+ других проблемы; слагаемые показаны рядом с числом;
- **затронутые страницы, первопричина, связанные проблемы** (у каждой основание связи), **рекомендация** и
  **доказательства** (скриншоты, URL, селекторы, запросы со статусом, текст из консоли).

В `current.json` группы лежат в поле `groups`, формат — как в английском README.

### Формат находки (`current.json`)

```ts
interface Finding {
  id: string;           // CC-001, CC-002... нумерация в рамках прогона
  fingerprint: string;  // постоянный хэш от rule + page + (selector или url) для сравнения прогонов
  severity: "critical" | "warning" | "notice";
  category: "interaction" | "layout" | "images" | "fonts" | "console"
          | "accessibility" | "seo" | "performance" | "security" | "network";
  rule: string;         // например "seo/missing-title"
  page: string;         // например "/checkout"
  message: string;      // короткое описание
  details: string;      // что именно наблюдалось
  selector?: string;    // самый короткий уникальный CSS-селектор
  url?: string;         // для ресурсов и запросов
  viewport?: string;    // например "375x812"
  screenshot?: string;  // относительный путь, только у critical и warning
  evidence?: Record<string, unknown>;  // статус, размер, длительность, стек...
}
```

Ещё в `current.json` лежат данные прогона (`tool`, `version`, `project`, `url`, `date`, `pages`, `viewports`,
`checks`, `errors`, `summary`), группы `groups` из раздела выше, а начиная со второго прогона — блок `comparison` с отпечатками исправленных, новых
и оставшихся находок.

### Что проверяет audit_project

| Категория | Правила (серьёзность) |
|---|---|
| console | необработанное исключение (critical), необработанный reject промиса (warning), `console.error` (warning); стек и файл:строка, повторы считаются |
| network | API 5xx (critical), API 4xx (warning, кроме 401/403 на странице входа), не загрузился JS/CSS (critical), картинка/шрифт (warning), запрос оборвался (warning), запрос дольше 1 с / 3 с (notice / warning) |
| seo | нет или пустой title, нет meta description, нет `lang`, нет `<h1>` (warning); несколько `<h1>`, пропуск уровней заголовков, нет canonical, favicon, Open Graph, robots.txt / sitemap.xml (notice) |
| images | картинка не загрузилась, нет `alt` (warning); файл больше 200 КБ / 1 МБ (notice / warning); натуральный размер больше показанного в 2+ раза (notice) |
| accessibility | правила [axe-core](https://github.com/dequelabs/axe-core) WCAG 2.x A/AA (critical / serious / moderate+minor → critical / warning / notice); элементы с `onclick`, недоступные с клавиатуры, нет видимого фокуса при Tab (warning) |
| layout | горизонтальный скролл с самым глубоким элементом за краем (warning), текст обрезан `overflow: hidden` (notice), зоны нажатия меньше 24×24 px на 375 px (notice); на каждой ширине |
| fonts | шрифт из `@font-face` не загрузился (warning), текст показан запасным шрифтом, потому что объявленный так и не загрузился (notice) |
| performance | load дольше 3 с, LCP больше 2,5 / 4 с, CLS больше 0,1 / 0,25, страница больше 3 МБ, больше 100 запросов, JS-файл больше 500 КБ, CSS-файл больше 150 КБ; пороги в [thresholds.py](codecheck_mcp/audit/thresholds.py) |
| interaction | кликает до 20 кнопок, ссылок `href="#"` / `javascript:` и `role="button"` на странице (каждый раз на свежей загрузке) и 2 с ждёт перехода, смены URL, запросов, изменений DOM, диалогов, новых вкладок; пропускает «выйти» / «удалить»; critical для `criticalSelectors`. Если клик сработал, но отправленный им запрос упал, — `interaction/action-request-failed` (critical для 5xx, warning для 4xx; 401/403 и 4xx от пустой формы не считаются). О критичном селекторе, по которому так и не кликнули, тоже сообщается: critical, если он не нашёл ни одного элемента ни на одной странице, warning, если элемент скрыт, селектор невалидный, кнопка похожа на удаление или кончился лимит кликов |
| security | сайт по HTTP (кроме localhost), mixed content (warning); нет CSP, `nosniff`, HSTS (notice); cookies без `Secure` или сессионные без `HttpOnly` (warning); открытые source maps (notice) |

Если axe и другая проверка нашли одно и то же (например, нет `alt` или `lang`), в отчёте будет одна запись.

## Попробовать на демо-магазине

[examples/demo-shop](examples/demo-shop) — маленький сайт с намеренными ошибками (ошибки в скриптах, битые
картинка и скрипт, API с ответом 500, горизонтальный скролл на телефоне, мёртвая кнопка «Checkout», кнопки
«Place order», чей запрос падает, страница без title), и «чистая» главная.

```bash
python examples/demo-shop/serve.py 8765
# и скажите агенту: запусти audit_project на http://127.0.0.1:8765/ с criticalSelectors ["#checkout", "#place-order"]
```

## Архитектура

```text
codecheck_mcp/
  server.py                 MCP-инструменты
  browser.py                запуск Playwright, локальный сервер для папки, блокировка чужих доменов
  checks/                   проверки быстрых инструментов (full_qa, test_*)
  audit/
    runner.py               audit_project: обход, проверки на каждой ширине, слияние дублей, отчёты
    thresholds.py           все пороги в одном месте
    core/                   finding, fingerprint, selector, screenshot, crawler, session (события страницы)
    checks/                 один модуль на категорию; в каждом run(page, ctx) -> list[Finding]
    report/                 json_report, markdown, diff, priority (группировка)
  vendor/axe.min.js         axe-core 4.13.0 без изменений (MPL-2.0)
```

Каждая страница загружается один раз на каждую ширину; события консоли и сети записываются ещё до начала
загрузки, потом все проверки читают одну и ту же страницу. Проверки регистрируются в `audit/checks/__init__.py`.

## Безопасность самого сервера

- Только чтение: проверяемый проект не изменяется.
- Страницы открываются в изолированном контексте браузера, без ваших cookies и сессий.
- Переходы на чужие домены блокируются; `audit_project` не заполняет и не отправляет формы с данными и пропускает
  кнопки, похожие на «выйти» или «удалить».
- Проверки безопасности пассивные: читаются заголовки, cookies и открытые файлы, сайт никто не атакует.
- Секреты, найденные `quick_security`, в отчётах маскируются.
- Проверяйте только свои проекты и сайты, на проверку которых у вас есть разрешение владельца.

## Известные ограничения

- Полный `audit_project` маленького сайта занимает около 30 с; страницы с большим числом мёртвых кнопок дольше (до
  2 с на клик). Для больших сайтов уменьшайте `maxPages` или сужайте `checks`.
- Console, network, SEO, images, fonts, accessibility, performance и security работают только на самой широкой
  ширине экрана; layout — на каждой.
- Для локальной папки не проверяются заголовки сервера и cookies: их отдаёт временный сервер, а не ваш проект.
- Видно только атрибут `onclick`, но не обработчики, добавленные через `addEventListener`.
- Размеры — это переданные байты: локальная папка отдаётся без сжатия, на реальном хостинге будет легче.
- Сравнение идёт только с предыдущим прогоном в той же папке отчётов.

## Планы

- Необязательная настройка сессии (cookies или скрипт входа), чтобы проверять страницы за логином.
- Проверять консоль и сеть на каждой ширине экрана.
- Ограничение общей длительности для очень больших сайтов.
- Проверить на macOS и Linux.

## Разработка

```bash
pip install -e ".[dev]"
python -m playwright install chromium
pytest tests -q
ruff check codecheck_mcp tests
mypy codecheck_mcp
```

Тесты используют страницы с намеренными ошибками, «чистые» страницы, на которых не должно быть находок, и
регрессии, найденные на реальных сайтах. См. [CONTRIBUTING.md](CONTRIBUTING.md).

## Лицензия

MIT, см. [LICENSE](LICENSE). `codecheck_mcp/vendor/axe.min.js` — это [axe-core](https://github.com/dequelabs/axe-core)
от Deque Systems под лицензией MPL-2.0, см. [codecheck_mcp/vendor](codecheck_mcp/vendor).
