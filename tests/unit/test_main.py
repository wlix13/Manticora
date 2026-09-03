import sys
from pathlib import Path

import pytest

from manticora.__main__ import main


def run(monkeypatch: pytest.MonkeyPatch, *args: str) -> int | str | None:
    monkeypatch.setattr(sys, "argv", ["manticora", *args])
    with pytest.raises(SystemExit) as exc:
        main()
    return exc.value.code


def test_usage_errors_exit_two_with_the_click_message(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert run(monkeypatch, "records", "add", "www.example.com", "BOGUS", "x") == 2
    assert "'BOGUS' is not one of" in capsys.readouterr().err


def test_manticora_errors_exit_one(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert run(monkeypatch, "records", "add", "www.example.com", "A", "1.2.3.4") == 1
    assert "Error:" in capsys.readouterr().err
