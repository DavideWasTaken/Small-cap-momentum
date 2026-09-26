from __future__ import annotations

from pathlib import Path

from smallcap_bt.data import load_cache


def test_load_cache_handles_mixed_dst_offsets(tmp_path: Path):
    path = tmp_path / "mixed_offsets.csv"
    path.write_text(
        "Datetime,Open,High,Low,Close,Volume\n"
        "2026-11-01 01:30:00-04:00,1,2,0.5,1.5,100\n"
        "2026-11-01 01:30:00-05:00,1.5,2,1,1.8,200\n",
        encoding="utf-8",
    )
    frame = load_cache(path, "America/New_York")
    assert len(frame) == 2
    assert str(frame.index.tz) == "America/New_York"
    assert not frame.index.duplicated().any()
