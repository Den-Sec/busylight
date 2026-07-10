# BusyLight Presence

Auto-switch your BusyLight to **In Call** while any application on
your computer is using the microphone. Works with Zoom, Teams, Meet,
Discord, Slack huddle, FaceTime, Skype — anything that asks the
operating system for a capture device. Falls back to whatever state
you last picked manually when you hang up.

Currently Windows-first. macOS and Linux back-ends are stubbed for
later.

## How it knows you're on a call

It does **not** integrate with Zoom / Teams / Google's APIs and so
needs no OAuth, no SaaS account, no permissions. It only asks Windows
one question: *"is any installed app actively using the microphone right
now?"* The answer lives in the registry under
`HKCU\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone`
— Windows itself writes `LastUsedTimeStop = 0` while an app holds the
device and a real timestamp when it releases it.

Privacy boundary: the helper learns the **filename** of capturing apps
(e.g. `Zoom.exe`, `Teams.exe`), not their audio.

## Quick start

```powershell
# from the presence_helper/ directory
.\scripts\run.ps1
```

On first launch the helper looks for a config file at
`%APPDATA%\BusyLight\presence.ini`. Create it like this:

```ini
[busylight]
host = busylight-XXXX.local
pin  = 1234
poll_seconds = 2.0
default_state = AVAILABLE
```

…or skip the file and use environment variables:

```powershell
$env:BUSYLIGHT_HOST = "busylight-f5f0.local"
$env:BUSYLIGHT_PIN  = "1234"
.\scripts\run.ps1
```

The helper logs every state transition. Start a Teams / Zoom / Meet
call and watch the BusyLight turn red, hang up and it goes back to
whatever you had it set to.

## Run as a single .exe

```powershell
.\scripts\build_exe.ps1
```

Produces `dist\BusyLightPresence.exe`. Drop it into your
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup` folder to
launch it at login.

## Configuration reference

| Key             | Env var                       | Default       | What it does                                                                                                       |
| --------------- | ----------------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------ |
| `host`          | `BUSYLIGHT_HOST`              | —             | The mDNS name or IP of your BusyLight, e.g. `busylight-f5f0.local`. Required.                                      |
| `pin`           | `BUSYLIGHT_PIN`               | —             | Your PIN. Required.                                                                                                |
| `poll_seconds`  | `BUSYLIGHT_POLL_SECONDS`      | `2.0`         | How often to read the registry. 2 s feels instant in practice.                                                     |
| `default_state` | `BUSYLIGHT_DEFAULT_STATE`     | `AVAILABLE`   | What to fall back to when the mic goes idle if the helper has not yet seen a manual choice on the device.          |

## How it respects your manual choices

Every poll the helper reads `/api/state` from the device. If the
current state is neither `IN_CALL` nor the last one *it* pushed, it
treats that as "the user just changed it from the web UI" and stores
it as the new manual baseline. Hang up the call and the light returns
to that state, not to the helper's default. Pick a state from the web
UI mid-call and the helper will keep `IN_CALL` for now (your video
call is still going) but restore your new pick when you hang up.

## Claude mode (optional)

Have the BusyLight double as a Claude Code activity light: **red while
Claude is working, green when it's idle**, driven entirely by USB
serial — no cloud, no polling.

```powershell
busylight-claude on      # arm the mode (also flips to green/idle now)
busylight-claude off     # disarm it; leaves the light as-is
busylight-claude status  # prints "on" or "off"
```

The tray icon also has an **On/Off** toggle for the same switch, for
anyone who'd rather not touch a terminal.

Arming the mode alone does nothing until Claude Code hooks are wired
up to call it. The easiest way is:

```powershell
busylight-claude install-hooks
```

This edits `~/.claude/settings.json` for you. It's **non-destructive**:
it takes a backup first (`settings.json.busylight.bak` next to the
original), preserves every key and hook you already have, and is
idempotent — running it again never adds duplicate entries. To remove
only the hooks it added (leaving any of your other hooks untouched):

```powershell
busylight-claude uninstall-hooks
```

If you'd rather wire it up by hand, or want to see what
`install-hooks` writes, add this to `~/.claude/settings.json`
(adjust the command to a full path to `busylight-claude.exe`, or
`python -m busylight_presence.claude_light` from the `presence_helper`
venv, if it's not on your `PATH`):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "busylight-claude working" }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "busylight-claude idle" }] }
    ],
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "busylight-claude idle" }] }
    ]
  }
}
```

`UserPromptSubmit` fires when you send Claude a new turn (light turns
red / `BUSY`); `Stop` and `SessionStart` fire when Claude finishes
responding or a session starts (light turns green / `AVAILABLE`).
Every hook call is best-effort over USB serial and never fails your
Claude Code turn, even with no BusyLight plugged in.

## Limitations / future work

- macOS and Linux back-ends are no-ops. PRs welcome.
- Some web browsers (Brave's Tor mode, certain Firefox versions) talk
  to the audio device through their own sandbox and may not always
  show up in the Capability Access Manager. They usually do; report
  bugs if you find an outlier.
- No tray icon yet. The helper runs in a console window.
- HTTPS is not supported (the device serves plain HTTP on the LAN).
