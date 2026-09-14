import argparse
import json
import os
import sys

# Обеспечиваем корректный вывод UTF-8 в консоли Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from core.ai_client import DEFAULT_API_KEY
from core import storage
from core import rule_exporter
from core.orchestrator import run_agent_pipeline


def _print_pretty(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(
        prog="threat-intel",
        description="Двух-агентная система анализа фишинговых угроз (Сборщик → Аналитик) "
                    "со сбором данных через изолированную песочницу "
                    "и генерацией компактных сигнатур для локального антиспама.",
    )
    sub = parser.add_subparsers(dest="cmd")

    # analyze
    a = sub.add_parser("analyze", help="Проанализировать образец (url / file / html) через связку Сборщик → Аналитик")
    a.add_argument("input", help="URL, путь к файлу, или текст HTML")
    a.add_argument("--type", choices=["url", "file", "html"], default="url",
                   help="Тип входа (по умолчанию url)")
    a.add_argument("--json", action="store_true", help="Вывести отчёт как JSON")

    # report
    r = sub.add_parser("report", help="Показать отчёт по образцу")
    r.add_argument("id", type=int, help="ID образца в БД")
    r.add_argument("--json", action="store_true", help="Вывести как JSON")

    # trace — цепочка рассуждений агентов
    t = sub.add_parser("trace", help="Показать шаги агентов (какие тулзы, что видели, к чему пришли)")
    t.add_argument("id", type=int, help="ID образца в БД")
    t.add_argument("--agent", choices=["collector_agent", "analyst_agent"],
                   help="Только один агент")
    t.add_argument("--full", action="store_true", help="Не обрезать длинные тексты")
    t.add_argument("--json", action="store_true", help="Вывести как JSON")

    # stats
    s = sub.add_parser("stats", help="Краткая статистика по базе")
    s.add_argument("--json", action="store_true")

    # campaigns (Task.md: Campaign Tracking)
    c = sub.add_parser("campaigns", help="Список отслеживаемых фишинговых кампаний")
    c.add_argument("--json", action="store_true", help="Вывести как JSON")

    # export-rules (Task.md: Экспорт компактных правил для антиспама)
    er = sub.add_parser("export-rules", help="Экспорт компактных правил для локального антиспама")
    er.add_argument("--format", choices=["json", "rspamd", "yara"], default="json",
                    help="Формат правил (json / rspamd / yara, по умолчанию json)")
    er.add_argument("--out", help="Путь для сохранения файла (если не задан — вывод в stdout)")

    args = parser.parse_args()

    # Контейнер агента запускается как `python main.py` без аргументов.
    # В этом режиме он не должен завершаться — ждёт CLI-команд через docker exec.
    if args.cmd is None:
        parser.print_help()
        import time
        if os.environ.get("SERVICE_ROLE") == "ai_agents":
            print("\n[threat-agents] Контейнер агента запущен (CLI-режим).\n"
                  "Используйте: docker exec threat_agents python main.py analyze ... "
                  "| report <id> | stats", file=sys.stderr, flush=True)
            while True:
                time.sleep(3600)
        return

    if not DEFAULT_API_KEY:
        print("[Внимание] AI_API_KEY не задан. Бренд-определение и LLM-аналитика "
              "не будут работать, но сбор данных — да.", file=sys.stderr)

    if args.cmd == "analyze":
        print(f"[ThreatIntel] Анализ {args.type}: {args.input[:200]} (связка Сборщик → Аналитик)")
        result = run_agent_pipeline(args.type, args.input)
        if args.json:
            _print_pretty(result)
        else:
            if result.get("ok"):
                rep = result["report"]
                print(f"\n✅ Образец #{result['sample_id']} проанализирован.")
                print(f"   URL/объекты: {len(rep['urls'])}")
                print(f"   Артефакты:   {len(rep['artifacts'])}")
                brand_items = [f"{b['brand']} (целевой)" if b.get("in_target") else b["brand"] for b in rep["brands"]]
                print(f"   Бренд:       {brand_items or 'не определён'}")
                print(f"   Техники:     {[f['technique'] for f in rep['findings']] or 'нет'}")
                print(f"   Сигнатуры:   {len(rep['signatures'])} ({', '.join(sorted(set(s['kind'] for s in rep['signatures'])))})")
                col = result.get("collector", {})
                ana = result.get("analyst", {})
                print(f"   Сборщик:     шагов {col.get('steps', 0)}, "
                      f"файлов зафиксировано {col.get('files_registered', 0)}")
                print(f"   Аналитик:    шагов {ana.get('steps', 0)}")
                print(f"   Профиль:     {ana.get('report_path')}")
            else:
                print(f"\n❌ Ошибка: {result.get('error')}")

    elif args.cmd == "report":
        storage.init_db()
        conn = storage.get_conn()
        try:
            rep = storage.full_report(conn, args.id)
        finally:
            conn.close()
        if rep.get("sample") is None:
            print(f"Образец #{args.id} не найден.")
            sys.exit(1)
        if args.json:
            _print_pretty(rep)
        else:
            print(json.dumps(rep, ensure_ascii=False, indent=2, default=str))

    elif args.cmd == "trace":
        storage.init_db()
        conn = storage.get_conn()
        try:
            traces = storage.list_traces(conn, args.id)
        finally:
            conn.close()
        if args.agent:
            traces = [t for t in traces if t["agent_name"] == args.agent]
        if not traces:
            print(f"Трейсов по образцу #{args.id} нет (анализ запускался без агентов?).")
            sys.exit(1)
        # Сортировка: сначала все шаги сборщика, потом аналитика (внутри — по шагам)
        order = {"collector_agent": 0, "analyst_agent": 1}
        traces.sort(key=lambda t: (order.get(t["agent_name"], 9),
                                   t.get("step", 0), t.get("id", 0)))
        if args.json:
            _print_pretty(traces)
        else:
            cur_agent = None
            for t in traces:
                if t["agent_name"] != cur_agent:
                    cur_agent = t["agent_name"]
                    name = "СБОРЩИК" if cur_agent == "collector_agent" else "АНАЛИТИК"
                    print(f"\n{'=' * 62}\n  {name} ({cur_agent})\n{'=' * 62}")
                limit = None if args.full else 400
                content = (t.get("content") or "").strip()
                if limit and len(content) > limit:
                    content = content[:limit] + "… [--full]"
                kind = t["kind"]
                icon = {"action": "🛠️", "observation": "📊",
                        "final": "✅", "thought": "💭"}.get(kind, "·")
                print(f"\n— шаг {t['step']} · {icon} {kind}")
                if t.get("args"):
                    print(f"  аргументы: {json.dumps(t['args'], ensure_ascii=False)[:300]}")
                if content:
                    for line in content.split("\n"):
                        print(f"  {line}")

    elif args.cmd == "stats":
        storage.init_db()
        conn = storage.get_conn()
        try:
            counts = {
                "samples": conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0],
                "urls": conn.execute("SELECT COUNT(*) FROM urls").fetchone()[0],
                "artifacts": conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0],
                "brands": conn.execute("SELECT COUNT(*) FROM brands").fetchone()[0],
                "findings": conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0],
                "signatures": conn.execute("SELECT COUNT(*) FROM signatures").fetchone()[0],
                "campaigns": conn.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0],
            }
        finally:
            conn.close()
        if args.json:
            _print_pretty(counts)
        else:
            print("Статистика базы:")
            for k, v in counts.items():
                print(f"  {k:11}: {v}")

    elif args.cmd == "campaigns":
        storage.init_db()
        conn = storage.get_conn()
        try:
            camps = storage.list_campaigns(conn)
        finally:
            conn.close()
        if args.json:
            _print_pretty(camps)
        else:
            if not camps:
                print("Активных кампаний пока не зафиксировано.")
            else:
                print(f"Отслеживаемые фишинговые кампании ({len(camps)}):")
                for cp in camps:
                    b = cp.get("target_brand") or "—"
                    h = (cp.get("dom_hash") or "")[:12]
                    print(f"  • {cp['name']} | Бренд: {b} | Образцов: {cp['sample_count']} | DOM: {h}... | Активность: {cp['last_seen']}")

    elif args.cmd == "export-rules":
        storage.init_db()
        conn = storage.get_conn()
        try:
            if args.format == "json":
                data = rule_exporter.export_json_rulepack(conn)
                out_str = json.dumps(data, ensure_ascii=False, indent=2)
            elif args.format == "rspamd":
                out_str = rule_exporter.export_rspamd_rules(conn)
            elif args.format == "yara":
                out_str = rule_exporter.export_yara_rules(conn)
        finally:
            conn.close()

        if args.out:
            from pathlib import Path
            Path(args.out).write_text(out_str, encoding="utf-8")
            print(f"Правила успешно экспортированы в {args.out} (формат: {args.format})")
        else:
            print(out_str)


if __name__ == "__main__":
    main()