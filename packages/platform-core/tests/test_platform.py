"""platform-core 最小集测试：trace_id 格式、配置加载、结构化日志含 trace_id。"""

from __future__ import annotations

import json
import logging

import pytest

from platform_core import config, logging as plog, trace


def test_trace_id_format():
    tid = trace.new_trace_id()
    assert trace.is_valid_trace_id(tid)
    assert trace.is_valid_trace_id("bad") is False


def test_settings_requires_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        config.Settings.from_env()


def test_settings_reads_urls(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5432/db")
    monkeypatch.setenv("SVC_ROUTE_ENGINE", "http://re:1")
    s = config.Settings.from_env()
    assert s.database_url.startswith("postgresql://"), "psycopg 方言前缀应被剥掉"
    assert s.route_engine_url == "http://re:1"


def test_json_log_contains_trace_id():
    plog.configure(logging.DEBUG)
    logger = logging.getLogger("t")
    captured = []

    class Cap(logging.StreamHandler):
        def emit(self, record):
            captured.append(plog.JsonFormatter().format(record))

    logger.handlers = [Cap()]
    plog.log(logger, logging.INFO, "工具调用", trace_id="tr_abc123", tool_code="poi.search")
    payload = json.loads(captured[0])
    assert payload["trace_id"] == "tr_abc123"
    assert payload["tool_code"] == "poi.search"
