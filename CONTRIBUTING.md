# Contributing

Thanks for your interest in BusyLight. This is a hobby / side product
project, so contributions are welcome and there are no enterprise hoops.

## Quick checklist before opening a PR

- [ ] `pio test` (firmware) is green for the env(s) you touched.
- [ ] `pytest --cov` (wizard) is green, and coverage on the files you
      touched is not lower than before.
- [ ] Lint passes (`ruff check`, `clang-format --dry-run --Werror`).
- [ ] `pre-commit run --all-files` is green if you have the hook installed.
- [ ] `CHANGELOG.md` has an `[Unreleased]` entry describing what you did.
- [ ] You signed your commits if you usually do; otherwise no requirement.

## Setting up the dev environment

```powershell
# Firmware
pip install --user platformio
cd firmware
pio run               # builds everything once and downloads toolchains

# Wizard
cd ..\windows_setup
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest

# Pre-commit (optional but recommended)
.\.venv\Scripts\python.exe -m pip install pre-commit
pre-commit install
```

## Commit style

We use [Conventional Commits](https://www.conventionalcommits.org/). A few
examples:

- `fix(serial): wait for USB CDC enumeration before handshake`
- `feat(auth): add PBKDF2 PIN hashing with per-device salt`
- `docs(readme): document the AP captive portal fallback`
- `refactor(api): replace DynamicJsonDocument with JsonDocument`

Breaking changes should use a `!` after the type or a `BREAKING CHANGE:`
footer.

## Branching

- `main` always builds and ships. The `release.yml` workflow ships a
  GitHub release on tag push.
- Feature work happens on short-lived branches named `feat/...`,
  `fix/...`, etc. Squash-merge into `main`.

## Tests

- Firmware: Unity, under `firmware/test/test_<module>/test_main.cpp`. A
  test module is a folder; PlatformIO discovers them automatically.
  Modules without hardware dependencies (`auth`, `led_engine`,
  `config_store` with mock NVS, `hostname`) should also build under the
  `native` PlatformIO env so they can run in CI without an ESP32.
- Wizard: pytest, in `windows_setup/tests/`. Use `FakeSerial` (already
  defined in `test_serial_protocol.py`) to mock device responses; do not
  open a real COM port from a unit test.

## What deserves a separate PR

- A handshake fix should not also rewrite the LED engine. Keep PRs scoped
  to one topic so reviewers can reason about them.
- README and code changes are fine in the same PR if they describe the
  same feature.

## What lives where

| Topic            | Files                                                      |
| ---------------- | ---------------------------------------------------------- |
| LED state machine| `firmware/src/led_engine.{h,cpp}`                          |
| Auth + PBKDF2    | `firmware/src/auth.{h,cpp}`                                |
| HTTP API         | `firmware/src/api_server.{h,cpp}`                          |
| Persistent state | `firmware/src/config_store.{h,cpp}`                        |
| AP captive portal| `firmware/src/ap_portal.{h,cpp}`                           |
| Boot / loop      | `firmware/src/main.cpp`                                    |
| Web UI           | `firmware/data/*`                                          |
| Wizard protocol  | `windows_setup/src/busylight_setup/serial_protocol.py`     |
| Wizard UI        | `windows_setup/src/busylight_setup/app.py`                 |

If you are not sure where something belongs, open an issue first and we
will talk it through.
