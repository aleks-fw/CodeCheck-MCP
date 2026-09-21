<p align="center">
  <img src="assets/banner.svg" alt="CodeCheck MCP" width="100%">
</p>

<h1 align="center">CodeCheck MCP</h1>

<p align="center">
  <a href="#установка">Установка</a> ·
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

MCP-сервер, который **сам тестирует готовый веб-проект**: открывает сайт в настоящем браузере (Playwright), жмёт
кнопки, смотрит вёрстку на пяти ширинах экрана, проверяет шрифты, картинки и базовую безопасность. Вашему
ИИ-агенту он отдаёт сводку и `report.md` со скриншотами, где каждая проблема обведена красным.

Проверялось на Windows и Python 3.14. Другие ОС и версии Python не проверялись.

| | |
|---|---|
| **Настоящий браузер** | Chromium через Playwright: реальные клики, реальная вёрстка, реальные шрифты. Ничего не угадывается по исходному коду. |
| **Находит то, что видит пользователь** | Мёртвые кнопки, наезжающий и обрезанный текст, горизонтальный скролл, низкий контраст, битые картинки, разные шрифты. |
| **Доказательства, а не мнения** | У каждой находки есть скриншот и CSS-селектор. Только измеримые правила, без вердиктов «некрасиво». |
| **Лёгкая проверка безопасности** | Секреты в файлах и истории git, `.env` в git, нет заголовков безопасности, небезопасные cookies. |
| **Безопасен по устройству** | Ваш проект только читается, браузер изолирован, внешние переходы заблокированы, секреты в отчётах замаскированы. |

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
      "command": "<путь>/codecheck-env/Scripts/codecheck-mcp"
    }
  }
}
```

`<путь>` — абсолютный путь к папке, где вы создали окружение. Перезапустите клиент, и в списке MCP появится `codecheck`.

### Если вы ИИ-агент

Установите по инструкции из [llms-install.md](llms-install.md).

## Использование

Скажите агенту, например: «Прогони full_qa на `D:\мой-сайт`» или «Проверь test_layout для https://example.com на
ширинах 375 и 1440». `target` — это URL или путь к папке/файлу проекта (для папки поднимается временный
локальный сервер).

## Инструменты

| Инструмент | Что проверяет |
|---|---|
| `full_qa(target, max_pages=10)` | Всё ниже сразу |
| `test_interactions(target)` | Мёртвые кнопки; отключённые, что всё равно реагируют; «кликабельный» вид без реакции; перекрытые кнопки; форма уходит с пустыми обязательными полями; двойной клик шлёт запрос дважды; битые якоря и ссылки-заглушки |
| `test_layout(target, widths=[...])` | На ширинах 320/375/768/1024/1440: наложение текста, обрезанный текст, горизонтальный скролл, контраст текста (в том числе на картинках), мелкие зоны нажатия |
| `test_fonts(target)` | Число шрифтов, шрифты-«чужаки», незагрузившиеся веб-шрифты, разброс размеров, иерархия заголовков |
| `test_images(target)` | Битые, растянутые, «мыльные», тяжёлые картинки, нет `alt` |
| `quick_security(target)` | Секреты в файлах и истории git, `.env` в git, нет `.gitignore`; у сайтов по URL: CSP, HSTS, X-Frame-Options, nosniff, Referrer-Policy, HTTP, mixed content, флаги cookie |

Отчёты пишутся в `~/codecheck-reports/<дата-время>/report.md`. Папку можно сменить переменной окружения
`CODECHECK_REPORTS_DIR`.

## Безопасность самого сервера

- Только чтение: проверяемый проект не изменяется.
- Клики выполняются в изолированном контексте браузера, без ваших cookies и сессий.
- Переходы на внешние домены блокируются и записываются в отчёт; внешние подресурсы грузятся с таймаутом 5 секунд.
- Секреты в отчёте маскируются (показаны первые 4 и последние 2 символа).
- Проверяйте только свои проекты и сайты, на проверку которых у вас есть разрешение владельца.

## Разработка

```bash
pip install -e ".[test]"
python -m playwright install chromium
pytest tests -q
```

Тесты используют HTML-фикстуры с заведомыми багами, «чистые» страницы и регрессии, найденные на реальном сайте.
См. [CONTRIBUTING.md](CONTRIBUTING.md).

## Лицензия

MIT, см. [LICENSE](LICENSE).
