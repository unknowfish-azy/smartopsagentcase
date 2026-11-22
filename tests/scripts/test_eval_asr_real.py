"""scripts/eval_asr_real.py 守卫测试（只测纯函数，不加载 whisper）。"""

import json

import pytest

from scripts import eval_asr_real


def test_load_index_reads_cues_format(tmp_path):
    index = tmp_path / "index.json"
    index.write_text(
        json.dumps({"count": 2, "cues": [{"file": "a.wav", "text": "打开知识库"}]}),
        encoding="utf-8",
    )

    rows = eval_asr_real._load_index(index, "cues")

    assert rows == [{"file": "a.wav", "text": "打开知识库"}]


def test_load_index_reads_top_level_list(tmp_path):
    index = tmp_path / "index.json"
    index.write_text(
        json.dumps([{"file": "a.wav", "text": "甲"}, {"file": "b.wav", "text": "乙"}]),
        encoding="utf-8",
    )

    rows = eval_asr_real._load_index(index, "list")

    assert [row["file"] for row in rows] == ["a.wav", "b.wav"]


def test_load_index_skips_entries_without_text(tmp_path):
    index = tmp_path / "index.json"
    index.write_text(
        json.dumps({"cues": [{"file": "a.wav"}, {"file": "b.wav", "text": "乙"}]}),
        encoding="utf-8",
    )

    rows = eval_asr_real._load_index(index, "cues")

    assert rows == [{"file": "b.wav", "text": "乙"}]


def test_normalize_and_edit_distance_align_with_eval_asr():
    assert eval_asr_real._normalize(" 打开知识库。 ") == "打开知识库"
    assert eval_asr_real._edit_distance("打开知识库", "打开支持库") == 2
    assert eval_asr_real._edit_distance("", "abc") == 3


def test_load_index_rejects_missing_cues(tmp_path):
    index = tmp_path / "index.json"
    index.write_text(json.dumps([{"file": "a.wav", "text": "甲"}]), encoding="utf-8")

    with pytest.raises(SystemExit):
        eval_asr_real._load_index(index, "cues")
