"""Screenshot the settings window briefly. Smoke check only."""

import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from PIL import ImageGrab

from busylight_presence.settings_window import SettingsWindow


def main(out_path: Path) -> None:
    cfg = SimpleNamespace(
        host="",
        pin="",
        poll_seconds=2.0,
        default_state="AVAILABLE",
        config_path=Path("test-presence.ini"),
    )

    settings = SettingsWindow(cfg=cfg, on_save=lambda c: None)

    def grab_and_quit() -> None:
        time.sleep(1.8)
        try:
            root = settings._root
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
                if settings._root is not None:
                    settings._root.after(0, settings._root.destroy)
            except Exception:
                pass

    threading.Thread(target=grab_and_quit, daemon=True).start()
    settings.open()


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("settings.png")
    main(out)
