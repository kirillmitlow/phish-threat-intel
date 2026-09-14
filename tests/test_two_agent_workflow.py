import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import sqlite3

from core.orchestrator import run_two_agent_pipeline, run_agent_pipeline
from core import storage


def test_two_agent_workflow_execution(monkeypatch, tmp_path):
    db_path = tmp_path / "test_analysis.db"
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()

    monkeypatch.setattr("core.storage.DEFAULT_DB_PATH", str(db_path))
    monkeypatch.setattr("core.orchestrator.ARTIFACTS_DIR", artifacts_dir)
    monkeypatch.setattr("core.pipeline.ARTIFACTS_DIR", artifacts_dir)

    # 1. Мокаем первичное создание/сбор
    mock_seed = {
        "ok": True,
        "final_url": "https://phish-bank.com/login",
        "redirect_chain": ["https://phish-bank.com/start", "https://phish-bank.com/login"],
        "links": ["https://phish-bank.com/login", "https://c2.xyz/steal"],
        "dom_size": 1500,
        "findings": [{"technique": "credential_form", "severity": "high"}],
    }

    # 2. Мокаем результаты агентов
    mock_collector = MagicMock()
    mock_collector.run.return_value = {
        "result": "Собрал страницу, редиректы и форму ввода логина/пароля.",
        "trace": [
            {"step": 1, "kind": "action", "content": "render_page", "args": {"url": "https://phish-bank.com"}},
            {"step": 2, "kind": "observation", "content": "https://phish-bank.com/login redirected to https://c2.xyz/steal"},
            {"step": 3, "kind": "final", "content": "Готово, всё собрано"}
        ]
    }

    mock_analyst = MagicMock()
    mock_analyst.run.return_value = {
        "result": "## Threat Intelligence Profile\n- Имитируемый бренд: Сбер\n- Техники: credential_form\n- Уверенность: 0.95",
        "trace": [
            {"step": 1, "kind": "action", "content": "analyze_screenshot", "args": {}},
            {"step": 2, "kind": "final", "content": "Вердикт: фишинг банка"}
        ]
    }

    with patch("core.orchestrator.collect_url", return_value=mock_seed) as mock_coll_url, \
         patch("agents.base_agent.BaseAgent.from_config") as mock_from_config, \
         patch("core.orchestrator.analyze_brand") as mock_analyze_brand, \
         patch("core.orchestrator.analyze_advanced_indicators", return_value={"dom_hash": "abc123hash"}):

        mock_from_config.side_effect = lambda cfg: mock_collector if cfg == "collector_agent" else mock_analyst

        result = run_two_agent_pipeline("url", "https://phish-bank.com")

        assert result["ok"] is True
        sample_id = result["sample_id"]
        assert sample_id > 0

        # Проверяем последовательный вызов обоих агентов
        assert mock_collector.run.called
        assert mock_analyst.run.called

        # Проверяем метрики в результате
        assert result["collector"]["steps"] == 3
        assert result["analyst"]["steps"] == 2
        assert "Threat Intelligence Profile" in result["analyst"]["result"]

        # Проверяем записи в базе данных
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        sample = conn.execute("SELECT * FROM samples WHERE id = ?", (sample_id,)).fetchone()
        assert sample["status"] == "analyzed"

        # Проверяем сохранение цепочки трейсов обоих агентов
        traces = conn.execute("SELECT * FROM agent_traces WHERE sample_id = ?", (sample_id,)).fetchall()
        agents_in_trace = {t["agent_name"] for t in traces}
        assert "collector_agent" in agents_in_trace
        assert "analyst_agent" in agents_in_trace

        conn.close()


def test_cli_mode_flag_removed():
    from main import main
    import sys

    # Проверяем, что передача --mode вызывает ошибку аргументов
    with patch.object(sys, "argv", ["main.py", "analyze", "https://test.com", "--mode", "pipeline"]):
        with pytest.raises(SystemExit):
            main()
