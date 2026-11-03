"""demo CLI integration tests (real DB via DATABASE_URL)."""

from __future__ import annotations

import pytest
from route_engine.demo import main


def test_demo_happy_path(capsys):
    rc = main(["云雀优选超市", "巨幕星云影院"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "路线：" in out and "合计：" in out
    assert "elevator" in out


def test_demo_missing_poi_exits(capsys):
    with pytest.raises(SystemExit):
        main(["不存在店铺XYZ", "巨幕星云影院"])


def test_demo_usage_returns_2(capsys):
    assert main([]) == 2
