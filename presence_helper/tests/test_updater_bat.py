# presence_helper/tests/test_updater_bat.py
from __future__ import annotations

from pathlib import Path

from busylight_presence.updater import _write_self_replace_bat


def test_give_up_relaunches_old_exe(tmp_path, monkeypatch) -> None:
    # Redirect the bat/log into tmp so we don't touch %TEMP%.
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    new_exe = tmp_path / "BusyLightPresence-0.4.0.exe"
    target = tmp_path / "BusyLightPresence.exe"
    bat_path = _write_self_replace_bat(new_exe=new_exe, target=target)
    text = bat_path.read_text(encoding="ascii")

    relaunch = f'start "" "{target}"'
    # One relaunch on success, one on the give-up path = 2 total.
    assert text.count(relaunch) == 2
    # The give-up relaunch must sit inside the "gave up" branch.
    give_up_idx = text.index("gave up after")
    assert text.index(relaunch, give_up_idx) > give_up_idx
