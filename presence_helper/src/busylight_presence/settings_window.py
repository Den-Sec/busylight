"""Tiny Tkinter settings window — host, PIN, poll interval.

Opens on demand from the tray menu. Closes itself on save or cancel
without exiting the helper. Designed to feel like a one-page config
panel: minimal, no menu bar, no resize.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable

from .config import PresenceConfig


class SettingsWindow:
    """Modal-ish Toplevel that edits a `PresenceConfig` in place."""

    def __init__(
        self,
        cfg: PresenceConfig,
        on_save: Callable[[PresenceConfig], None],
    ) -> None:
        self.cfg = cfg
        self.on_save = on_save
        self._root: tk.Tk | None = None

    def open(self) -> None:
        if self._root is not None and self._root.winfo_exists():
            self._root.deiconify()
            self._root.lift()
            self._root.focus_force()
            return

        root = tk.Tk()
        root.title("BusyLight Presence — Settings")
        root.geometry("420x320")
        root.resizable(False, False)
        try:
            # Use the system default theme tweaks for a less Tk-1990 look.
            ttk.Style().theme_use("vista")
        except tk.TclError:
            pass

        outer = ttk.Frame(root, padding=18)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="BusyLight Presence",
            font=("Segoe UI Semibold", 13),
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                "Tells your BusyLight when any application starts "
                "using the microphone."
            ),
            foreground="#555",
            wraplength=380,
            justify="left",
        ).pack(anchor="w", pady=(0, 14))

        host_var = tk.StringVar(value=self.cfg.host)
        pin_var = tk.StringVar(value=self.cfg.pin)
        poll_var = tk.StringVar(value=str(self.cfg.poll_seconds))

        def add_row(label: str, var: tk.StringVar, show: str = "") -> ttk.Entry:
            ttk.Label(outer, text=label).pack(anchor="w")
            entry = ttk.Entry(outer, textvariable=var, show=show)
            entry.pack(fill="x", pady=(2, 10))
            return entry

        add_row("BusyLight host (mDNS or IP)", host_var)
        add_row("Access PIN", pin_var, show="•")
        add_row("Poll interval (seconds)", poll_var)

        msg_var = tk.StringVar(value="")
        ttk.Label(outer, textvariable=msg_var, foreground="#a13").pack(
            anchor="w", pady=(2, 8)
        )

        btn_row = ttk.Frame(outer)
        btn_row.pack(fill="x")

        def do_save() -> None:
            try:
                new_cfg = PresenceConfig(
                    host=host_var.get().strip(),
                    pin=pin_var.get().strip(),
                    poll_seconds=float(poll_var.get().strip() or "2"),
                    default_state=self.cfg.default_state,
                    config_path=self.cfg.config_path,
                )
                new_cfg.ensure_valid()
            except (ValueError, TypeError) as e:
                msg_var.set(str(e))
                return

            try:
                new_cfg.save()
            except OSError as e:
                msg_var.set(f"could not save: {e}")
                return

            self.on_save(new_cfg)
            self.cfg = new_cfg
            msg_var.set("Saved.")
            root.after(700, root.withdraw)

        ttk.Button(btn_row, text="Cancel", command=root.withdraw).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(btn_row, text="Save", command=do_save).pack(side="right")

        # Closing the X just hides the window so the helper keeps running.
        root.protocol("WM_DELETE_WINDOW", root.withdraw)
        self._root = root

    def pump(self) -> None:
        """Process pending Tk events. Call from the main loop."""
        if self._root is not None and self._root.winfo_exists():
            try:
                self._root.update()
            except tk.TclError:
                self._root = None

    def close(self) -> None:
        if self._root is not None and self._root.winfo_exists():
            try:
                self._root.destroy()
            except tk.TclError:
                pass
        self._root = None
