"""Embed the device's web UI directly inside the desktop app.

Instead of reimplementing every card the firmware already ships (Wi-Fi,
schedule, MQTT, OTA, ...), the tray click now opens a native WebView2
window pointed at `http://<device-ip>`. Same exact pages as opening
the device's mDNS hostname in Edge, just framed in a window labelled
"BusyLight" so it feels like a desktop app.

When the device isn't reachable over the network (no Wi-Fi configured,
or USB-only setup), we fall back to a tiny customtkinter card that
tells the user to run `BusyLightSetup.exe` first.
"""

from __future__ import annotations

import logging
import socket
import threading
import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk

from . import __version__
from .bead import render_bead
from .serial_client import SerialClient, SerialUnavailable, find_busylight_ports

log = logging.getLogger(__name__)


class WebViewWindow:
    """Native window that wraps the device's web UI."""

    def __init__(self, loop, on_open_settings: Callable[[], None]) -> None:
        self._loop = loop
        self._on_open_settings = on_open_settings

    def open(self) -> None:
        target_url = self._resolve_target_url()
        if target_url:
            self._open_webview(target_url)
        else:
            self._open_no_wifi_fallback()

    def close(self) -> None:
        # pywebview manages its own lifetime; the only thing we
        # actively own is the fallback ctk window, and that closes
        # itself when the user dismisses it.
        return

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------
    def _resolve_target_url(self) -> Optional[str]:
        """Best-effort find the device on the network.

        1. If we have a USB port, ask the firmware directly via
           `get_info` — it tells us its hostname + (if Wi-Fi is up) IP.
        2. Otherwise fall back to the configured `cfg.host`.
        Returns `None` if neither is reachable.
        """
        cfg = self._loop.cfg

        # Try Serial first (USB-connected: the most reliable signal).
        ports = find_busylight_ports()
        if ports:
            try:
                sc = SerialClient(port=ports[0])
                info = sc.get_info()
                host = info.get("host")
                ip = info.get("ip")
                wifi_up = info.get("wifi") is True
                if wifi_up and ip:
                    return f"http://{ip}"
                if wifi_up and host:
                    return f"http://{host}.local"
                log.info("device on USB but Wi-Fi is not up")
            except (SerialUnavailable, Exception) as e:  # noqa: BLE001
                log.debug("serial get_info failed: %s", e)

        # Fall back to the configured host. If it resolves, use it.
        host = (cfg.host or "").strip()
        if host:
            if self._resolves(host):
                return f"http://{host}"
            log.info("configured host %s does not resolve", host)

        return None

    @staticmethod
    def _resolves(host: str) -> bool:
        try:
            socket.gethostbyname(host)
            return True
        except OSError:
            return False

    # ------------------------------------------------------------------
    # WebView path (happy path)
    # ------------------------------------------------------------------
    def _open_webview(self, url: str) -> None:
        # `webview` *must* run on the main thread, and `webview.start`
        # blocks until the window closes. pystray invokes menu items
        # on the main thread on Windows, so calling `start` here is
        # safe: the tray stays alive (Windows shell keeps the icon),
        # and when the user closes the WebView the tray menu becomes
        # responsive again.
        import webview

        log.info("opening webview at %s", url)
        try:
            window = webview.create_window(
                title="BusyLight",
                url=url,
                width=1024,
                height=760,
                resizable=True,
                # Don't force focus — pystray's "default" left-click
                # already focuses us, and stealing focus a second time
                # can cause flicker on some Windows builds.
                background_color="#0b1116",
            )
            # On Windows, gui="edgechromium" picks the modern WebView2
            # runtime explicitly. If WebView2 isn't installed pywebview
            # will surface a clear error which we show via fallback.
            webview.start(gui="edgechromium", debug=False)
        except Exception as e:  # noqa: BLE001
            log.exception("webview failed to start: %s", e)
            self._open_webview_error(url, str(e))

    def _open_webview_error(self, url: str, error: str) -> None:
        root = ctk.CTk()
        root.title("BusyLight — WebView error")
        root.geometry("440x260")
        outer = ctk.CTkFrame(root, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=22, pady=20)

        ctk.CTkLabel(
            outer,
            text="Couldn't open the embedded web view",
            font=ctk.CTkFont("Segoe UI Semibold", 14),
            anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            outer,
            text=(
                "You can still reach the device's UI by opening this "
                f"address in your browser:\n\n{url}"
            ),
            wraplength=400,
            justify="left",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#5d6066",
        ).pack(fill="x", pady=(10, 14))
        ctk.CTkLabel(
            outer,
            text=f"Details: {error}",
            wraplength=400,
            justify="left",
            font=ctk.CTkFont("JetBrains Mono", 9),
            text_color="#a13",
        ).pack(fill="x", pady=(0, 10))

        ctk.CTkButton(
            outer,
            text="Open in browser",
            command=lambda: self._open_in_browser(url),
            fg_color="#34c759",
            hover_color="#2eaa4d",
        ).pack(side="left")
        ctk.CTkButton(
            outer,
            text="Close",
            command=root.destroy,
            fg_color="#e8eaee",
            hover_color="#dcdee2",
            text_color="#2a2d33",
        ).pack(side="right")

        root.mainloop()

    @staticmethod
    def _open_in_browser(url: str) -> None:
        import webbrowser
        webbrowser.open(url)

    # ------------------------------------------------------------------
    # No-WiFi fallback
    # ------------------------------------------------------------------
    def _open_no_wifi_fallback(self) -> None:
        """Tiny window explaining the user needs to provision Wi-Fi."""
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        root = ctk.CTk()
        root.title("BusyLight — set up Wi-Fi")
        root.geometry("460x420")
        root.resizable(False, False)

        outer = ctk.CTkFrame(root, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=24, pady=22)

        # Header: small bead + title
        head = ctk.CTkFrame(outer, fg_color="transparent")
        head.pack(fill="x")

        bead_img = render_bead("wifi_error", 44)
        ctk_bead = ctk.CTkImage(light_image=bead_img, size=(44, 44))
        b = ctk.CTkLabel(head, text="", image=ctk_bead)
        b.image = ctk_bead
        b.pack(side="left")
        ctk.CTkLabel(
            head,
            text="Wi-Fi not configured",
            font=ctk.CTkFont("Segoe UI Semibold", 17),
            anchor="w",
        ).pack(side="left", padx=(12, 0))

        ctk.CTkLabel(
            outer,
            text=(
                "Your BusyLight is connected over USB but isn't on a "
                "Wi-Fi network yet, so the device's full web interface "
                "isn't reachable. Tray-level controls (state, mic "
                "detection) keep working over USB."
            ),
            wraplength=400, justify="left",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#3a3d42",
        ).pack(fill="x", pady=(14, 12))

        # Step-by-step card
        card = ctk.CTkFrame(outer, corner_radius=12, fg_color="#f6f7f9")
        card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            card,
            text="To add a Wi-Fi network",
            font=ctk.CTkFont("Segoe UI Semibold", 11),
            text_color="#5d6066",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            card,
            text=(
                "1. Run BusyLightSetup.exe (from the same release)\n"
                "2. Pick your COM port, enter SSID + password + PIN\n"
                "3. The device reboots, joins the network, and this "
                "window will open the full web UI on next click"
            ),
            wraplength=400, justify="left",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#3a3d42",
        ).pack(fill="x", padx=14, pady=(0, 12))

        btn_row = ctk.CTkFrame(outer, fg_color="transparent")
        btn_row.pack(fill="x", pady=(8, 0))

        def launch_setup() -> None:
            import subprocess, sys, os
            # When frozen we sit next to BusyLightSetup.exe in the
            # download folder; otherwise fall back to PATH lookup.
            here = (
                os.path.dirname(sys.executable)
                if getattr(sys, "frozen", False)
                else os.getcwd()
            )
            candidate = os.path.join(here, "BusyLightSetup.exe")
            if os.path.exists(candidate):
                subprocess.Popen([candidate])
            else:
                # Just try PATH; show nothing if it fails — the label
                # below already tells the user what to do.
                try:
                    subprocess.Popen(["BusyLightSetup.exe"])
                except FileNotFoundError:
                    pass
            root.destroy()

        ctk.CTkButton(
            btn_row,
            text="Launch setup wizard",
            command=launch_setup,
            fg_color="#34c759",
            hover_color="#2eaa4d",
            height=38,
            corner_radius=10,
            font=ctk.CTkFont("Segoe UI Semibold", 11),
        ).pack(side="left")

        ctk.CTkButton(
            btn_row,
            text="Close",
            command=root.destroy,
            fg_color="#e8eaee",
            hover_color="#dcdee2",
            text_color="#2a2d33",
            height=38,
            corner_radius=10,
            font=ctk.CTkFont("Segoe UI Semibold", 11),
        ).pack(side="right")

        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.mainloop()
