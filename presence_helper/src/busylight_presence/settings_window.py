"""Premium settings window for BusyLight Presence.

customtkinter, coherent with the dashboard and the web UI:
  - LED bead header (the same Pillow-rendered bead the dashboard uses)
  - Live USB-detection banner (green if a port is present, amber if not)
  - "Wi-Fi" card with host + PIN — flagged optional because USB-only
    setups don't need either
  - "Polling" slider
  - "Default state" segmented control
"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk

from .bead import render_bead
from .config import PresenceConfig
from .serial_client import find_busylight_ports

log = logging.getLogger(__name__)


_VALID_DEFAULT_STATES = ("AVAILABLE", "BUSY", "AWAY", "IN_CALL")


class SettingsWindow:
    def __init__(
        self,
        cfg: PresenceConfig,
        on_save: Callable[[PresenceConfig], None],
        on_closed: Optional[Callable[[], None]] = None,
    ) -> None:
        self.cfg = cfg
        self.on_save = on_save
        self.on_closed = on_closed
        self._root: Optional[ctk.CTk] = None

    def open(self) -> None:
        if self._root is not None:
            try:
                if self._root.winfo_exists():
                    self._root.destroy()
            except tk.TclError:
                pass
            self._root = None

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        root = ctk.CTk()
        root.title("BusyLight Presence — Settings")
        root.geometry("470x720")
        root.resizable(False, False)

        outer = ctk.CTkFrame(root, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=24, pady=22)

        # ---- Header: small bead + title -----------------------------
        head = ctk.CTkFrame(outer, fg_color="transparent")
        head.pack(fill="x")

        bead_img = render_bead("available", 40)
        ctk_bead = ctk.CTkImage(light_image=bead_img, size=(40, 40))
        bead_lbl = ctk.CTkLabel(head, text="", image=ctk_bead)
        bead_lbl.image = ctk_bead
        bead_lbl.pack(side="left")

        ctk.CTkLabel(
            head,
            text="Settings",
            font=ctk.CTkFont("Segoe UI Semibold", 18),
            anchor="w",
        ).pack(side="left", padx=(12, 0))

        ctk.CTkLabel(
            outer,
            text=(
                "Tells your BusyLight when any application starts "
                "using the microphone."
            ),
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#5d6066",
            wraplength=400,
            anchor="w",
            justify="left",
        ).pack(fill="x", pady=(6, 18))

        # ---- Live USB banner ----------------------------------------
        usb_ports = find_busylight_ports()
        if usb_ports:
            banner_text = (
                f"Device detected over USB ({usb_ports[0]}).\n"
                "Wi-Fi settings below are optional."
            )
            banner_color = "#16744a"
            banner_bg = "#e6f4ec"
        else:
            banner_text = (
                "No USB device detected.\n"
                "Fill in Wi-Fi host + PIN below, or plug in the cable."
            )
            banner_color = "#a35a00"
            banner_bg = "#fdf3e1"

        banner = ctk.CTkFrame(outer, corner_radius=10, fg_color=banner_bg)
        banner.pack(fill="x")
        ctk.CTkLabel(
            banner,
            text=banner_text,
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=banner_color,
            justify="left",
            anchor="w",
            wraplength=380,
        ).pack(fill="x", padx=14, pady=10)

        # ---- Wi-Fi card --------------------------------------------
        host_var = tk.StringVar(value=self.cfg.host)
        pin_var = tk.StringVar(value=self.cfg.pin)

        wifi_card = self._card(outer, "Wi-Fi (optional)")
        ctk.CTkLabel(
            wifi_card,
            text="BusyLight host (mDNS or IP)",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#5d6066",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 2))
        ctk.CTkEntry(
            wifi_card,
            textvariable=host_var,
            font=ctk.CTkFont("JetBrains Mono", 12),
            placeholder_text="busylight-XXXX.local or 192.168.x.x",
            height=34,
        ).pack(fill="x", padx=14, pady=(0, 10))

        ctk.CTkLabel(
            wifi_card,
            text="Access PIN",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#5d6066",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 2))
        ctk.CTkEntry(
            wifi_card,
            textvariable=pin_var,
            show="•",
            font=ctk.CTkFont("JetBrains Mono", 12),
            placeholder_text="4–8 digits",
            height=34,
        ).pack(fill="x", padx=14, pady=(0, 14))

        # ---- Polling card ------------------------------------------
        poll_var = tk.DoubleVar(value=float(self.cfg.poll_seconds))
        poll_card = self._card(outer, "Polling")
        poll_row = ctk.CTkFrame(poll_card, fg_color="transparent")
        poll_row.pack(fill="x", padx=14, pady=(0, 12))

        poll_value_lbl = ctk.CTkLabel(
            poll_row,
            text=f"{poll_var.get():.1f}s",
            font=ctk.CTkFont("JetBrains Mono", 12),
            text_color="#3a3d42",
            width=50,
        )
        poll_value_lbl.pack(side="right")

        def _poll_changed(v: float) -> None:
            poll_var.set(round(v, 1))
            poll_value_lbl.configure(text=f"{v:.1f}s")

        slider = ctk.CTkSlider(
            poll_row,
            from_=0.5, to=5.0, number_of_steps=45,
            command=_poll_changed,
        )
        slider.set(poll_var.get())
        slider.pack(side="left", fill="x", expand=True, padx=(0, 12))

        # ---- Default state card ------------------------------------
        default_state_var = tk.StringVar(value=self.cfg.default_state)
        ds_card = self._card(outer, "Default state when mic is idle")
        ds_row = ctk.CTkFrame(ds_card, fg_color="transparent")
        ds_row.pack(fill="x", padx=14, pady=(0, 14))
        ctk.CTkSegmentedButton(
            ds_row,
            values=["AVAILABLE", "BUSY", "AWAY"],
            variable=default_state_var,
            font=ctk.CTkFont("Segoe UI Semibold", 10),
        ).pack(fill="x")

        # ---- Error message slot ------------------------------------
        msg_var = tk.StringVar(value="")
        ctk.CTkLabel(
            outer,
            textvariable=msg_var,
            font=ctk.CTkFont("Segoe UI", 11),
            text_color="#c0392b",
        ).pack(anchor="w", pady=(8, 6))

        # ---- Actions -----------------------------------------------
        btn_row = ctk.CTkFrame(outer, fg_color="transparent")
        btn_row.pack(fill="x", pady=(4, 0))

        def do_save() -> None:
            try:
                new_cfg = PresenceConfig(
                    host=host_var.get().strip(),
                    pin=pin_var.get().strip(),
                    poll_seconds=float(poll_var.get()),
                    default_state=default_state_var.get(),
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
            msg_var.set("")
            root.after(300, root.destroy)

        ctk.CTkButton(
            btn_row,
            text="Cancel",
            fg_color="#e8eaee",
            hover_color="#dcdee2",
            text_color="#2a2d33",
            font=ctk.CTkFont("Segoe UI Semibold", 11),
            height=36,
            corner_radius=9,
            command=root.destroy,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            btn_row,
            text="Save",
            fg_color="#34c759",
            hover_color="#2eaa4d",
            text_color="#ffffff",
            font=ctk.CTkFont("Segoe UI Semibold", 11),
            height=36,
            corner_radius=9,
            command=do_save,
        ).pack(side="right")

        def _on_close() -> None:
            try:
                root.destroy()
            except tk.TclError:
                pass

        root.protocol("WM_DELETE_WINDOW", _on_close)
        self._root = root
        root.mainloop()
        self._root = None

        if self.on_closed:
            try:
                self.on_closed()
            except Exception as e:  # noqa: BLE001
                log.debug("on_closed callback raised: %s", e)

    def close(self) -> None:
        if self._root is not None:
            try:
                self._root.destroy()
            except tk.TclError:
                pass
        self._root = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _card(self, parent: ctk.CTkFrame, title: str) -> ctk.CTkFrame:
        """A grey rounded section with a small section title above it."""
        ctk.CTkLabel(
            parent,
            text=title,
            font=ctk.CTkFont("Segoe UI Semibold", 11),
            text_color="#5d6066",
            anchor="w",
        ).pack(fill="x", pady=(14, 6))
        card = ctk.CTkFrame(parent, corner_radius=12, fg_color="#f6f7f9")
        card.pack(fill="x")
        # Spacer so the first widget inside isn't flush against the top edge.
        ctk.CTkLabel(card, text="", height=2).pack()
        return card
