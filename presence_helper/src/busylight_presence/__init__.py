"""BusyLight Presence — auto-switch the desk light when you go on a call.

Watches the operating system for any application using the microphone
(Zoom, Teams, Meet, Discord, Slack huddle, …) and tells the configured
BusyLight to switch to IN_CALL while the mic is in use. Restores the
previous manual state when the call ends.
"""

__version__ = "0.3.17"
