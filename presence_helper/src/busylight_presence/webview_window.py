"""Open the device's web UI inside a native WebView2 window.

Used as an *optional* button from the dashboard, never forced on the
user. If the WebView2 runtime is missing or pywebview can't start
for any reason, we fall back cleanly to opening the URL in the
system browser.
"""

from __future__ import annotations

import logging
import webbrowser

log = logging.getLogger(__name__)


def open_device_webui(url: str) -> None:
    """Open `url` in an embedded WebView2 window. Falls back to the
    system browser on any error so the user never gets stuck."""
    try:
        import webview  # type: ignore
    except Exception as e:  # noqa: BLE001
        log.info("pywebview not available (%s); opening browser", e)
        webbrowser.open(url)
        return

    try:
        webview.create_window(
            title="BusyLight",
            url=url,
            width=1024,
            height=760,
            resizable=True,
            background_color="#0b1116",
        )
        webview.start(gui="edgechromium", debug=False)
    except Exception as e:  # noqa: BLE001
        log.warning("webview start failed (%s); opening browser", e)
        webbrowser.open(url)
