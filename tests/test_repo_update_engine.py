from pathlib import Path

import repo_update_engine as rue


def test_repo_update_engine_create_append_replace_and_insert(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    rue.create_folder("sub")
    rue.create_file("sub/a.txt", "hello")
    assert Path("sub/a.txt").read_text(encoding="utf-8") == "hello"

    rue.append_file("sub/a.txt", "world")
    text = Path("sub/a.txt").read_text(encoding="utf-8")
    assert "world" in text

    rue.replace_text("sub/a.txt", "hello", "ciao")
    assert "ciao" in Path("sub/a.txt").read_text(encoding="utf-8")

    rue.insert_line("sub/a.txt", 1, "TOP")
    lines = Path("sub/a.txt").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "TOP"


def test_repo_update_engine_read_block():
    lines = ["line1\n", "line2\n", "EOF\n", "rest\n"]
    content, idx = rue.read_block(lines, 0)
    assert content == "line1\nline2\n"
    assert idx == 2
