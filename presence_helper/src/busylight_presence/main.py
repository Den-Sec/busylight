"""Entry point for the BusyLight Presence helper.

Polls the microphone state every ``poll_seconds`` and reflects it on
the configured BusyLight:

  mic_active == True  -> set state to IN_CALL
  mic_active == False -> restore the last "manual" state the user
                         set via the web UI (snapshot taken at startup
                         and re-fetched whenever it changes outside of
                         our own IN_CALL toggle)

Designed to be a 60-line state machine over a polling loop. No tray
icon, no GUI; that lives in ``tray.py`` (added later). For now the
helper runs in a console window and logs to stdout.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

from . import __version__
from .client import (
    BusyLightAuthError,
    BusyLightClient,
    BusyLightNetworkError,
)
from .config import PresenceConfig, load_config
from .mic_monitor import microphone_in_use, supported_platform

log = logging.getLogger("busylight_presence")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="busylight-presence",
        description=(
            "Watch the microphone and switch the BusyLight to IN_CALL "
            "while any app is capturing audio."
        ),
    )
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to a presence.ini config file. Defaults to per-OS user dir.",
    )
    p.add_argument(
        "--once",
        action="store_true",
        help="Read mic state once, push it, and exit. Useful for cron / testing.",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Debug logging.",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"busylight-presence {__version__}",
    )
    return p


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


class PresenceLoop:
    def __init__(self, cfg: PresenceConfig, client: BusyLightClient) -> None:
        self.cfg = cfg
        self.client = client
        self.running = True

        # The state the user picked manually. We restore this when the
        # mic becomes idle. We refresh it from the device whenever we
        # see "the current state on the device is NOT IN_CALL and NOT
        # the one we last set", which means the user (or another
        # controller) overrode us.
        self.last_manual_state: str = cfg.default_state
        self.last_pushed_state: str | None = None
        self.last_mic_in_use: bool | None = None

    def stop(self, *_args) -> None:  # noqa: ANN001
        log.info("shutting down")
        self.running = False

    def tick(self) -> None:
        usage = microphone_in_use()
        # Read the current state on the device. If a human pressed a
        # button in the web UI we want to honour it next time the mic
        # goes idle.
        try:
            current = self.client.get_state()
        except BusyLightNetworkError as e:
            log.warning("get_state failed: %s", e)
            current = None
        except BusyLightAuthError as e:
            log.warning("auth lost: %s", e)
            try:
                self.client.login()
            except (BusyLightAuthError, BusyLightNetworkError) as exc:
                log.error("re-login failed: %s", exc)
            return

        if current and current != "IN_CALL":
            if self.last_pushed_state != current:
                # Someone changed it outside of us — remember as the
                # baseline to restore.
                self.last_manual_state = current
                log.debug("learnt manual state -> %s", current)

        desired = "IN_CALL" if usage.in_use else self.last_manual_state

        # Only push when the desired state differs from what we
        # observed; this avoids hammering NVS on the device.
        if current == desired:
            self.last_pushed_state = desired
            self._log_transition(usage)
            return

        try:
            self.client.set_state(desired)
            self.last_pushed_state = desired
            self._log_transition(usage, set_to=desired)
        except BusyLightAuthError as e:
            log.warning("auth error while setting state: %s", e)
        except BusyLightNetworkError as e:
            log.warning("network error while setting state: %s", e)

    def _log_transition(self, usage, *, set_to: str | None = None) -> None:
        if usage.in_use == self.last_mic_in_use and set_to is None:
            return
        self.last_mic_in_use = usage.in_use
        if set_to:
            label = "→ %s" % set_to
        else:
            label = "(no change)"
        apps = ", ".join(usage.apps) if usage.apps else "—"
        log.info(
            "mic %s  apps=%s  %s",
            "ACTIVE" if usage.in_use else "idle",
            apps,
            label,
        )


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _setup_logging(args.verbose)

    if not supported_platform():
        log.warning(
            "presence detection is currently Windows-only; on other "
            "platforms the helper will not flip the light. Use the web "
            "UI to set the state manually."
        )

    try:
        cfg = load_config(args.config)
        cfg.ensure_valid()
    except (FileNotFoundError, ValueError) as e:
        log.error("config: %s", e)
        log.error(
            "Create %s with at least:\n"
            "  [busylight]\n"
            "  host = busylight-XXXX.local\n"
            "  pin  = 1234\n"
            "or set the BUSYLIGHT_HOST and BUSYLIGHT_PIN env vars.",
            args.config or "<your config path>",
        )
        return 2

    client = BusyLightClient(host=cfg.host, pin=cfg.pin)
    try:
        client.login()
    except BusyLightAuthError as e:
        log.error("login failed: %s", e)
        return 3
    except BusyLightNetworkError as e:
        log.error("cannot reach BusyLight at %s: %s", cfg.host, e)
        return 4

    loop = PresenceLoop(cfg, client)
    # Capture the device's current state as the baseline manual state.
    try:
        current = client.get_state()
        if current and current != "IN_CALL":
            loop.last_manual_state = current
            loop.last_pushed_state = current
    except (BusyLightAuthError, BusyLightNetworkError):
        pass

    signal.signal(signal.SIGINT, loop.stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, loop.stop)

    log.info(
        "watching %s every %.1fs (baseline state: %s)",
        cfg.host,
        cfg.poll_seconds,
        loop.last_manual_state,
    )

    if args.once:
        loop.tick()
        return 0

    while loop.running:
        try:
            loop.tick()
        except Exception as e:  # noqa: BLE001
            log.exception("unhandled error in tick: %s", e)
        time.sleep(cfg.poll_seconds)

    return 0


if __name__ == "__main__":
    sys.exit(main())
