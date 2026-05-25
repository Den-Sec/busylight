"""Render the dashboard briefly and save a screenshot. Smoke check only."""

import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PIL import ImageGrab

from busylight_presence.dashboard_window import DashboardWindow


class _FakeClient:
    current_mode = "serial"
    serial_port = "COM3"


def main(out_path: Path, state: str = "BUSY") -> None:
    cfg = SimpleNamespace(host="", pin="", poll_seconds=2.0,
                          default_state="AVAILABLE")
    loop = SimpleNamespace(
        cfg=cfg,
        client=_FakeClient(),
        last_pushed_state=state,
        last_manual_state="AVAILABLE",
        stats={"AVAILABLE": 7800, "BUSY": 2100, "IN_CALL": 3720,
               "AWAY": 60, "OFF": 0},
    )

    dashboard = DashboardWindow(
        loop,
        on_open_settings=lambda: None,
        on_set_state=lambda s: None,
        on_open_webui=lambda url: None,
    )

    def grab_and_quit() -> None:
        time.sleep(2.0)
        try:
            root = dashboard._root
            if root is None:
                return
            root.update_idletasks()
            x = root.winfo_rootx()
            y = root.winfo_rooty()
            w = root.winfo_width()
            h = root.winfo_height()
            img = ImageGrab.grab(bbox=(x - 4, y - 4, x + w + 4, y + h + 32))
            img.save(out_path)
            print(f"Saved {out_path}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"screenshot failed: {e}", flush=True)
        finally:
            try:
                if dashboard._root is not None:
                    dashboard._root.after(0, dashboard._root.destroy)
            except Exception:
                pass

    threading.Thread(target=grab_and_quit, daemon=True).start()
    dashboard.open()


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dashboard.png")
    state = sys.argv[2] if len(sys.argv) > 2 else "BUSY"
    main(out, state)
