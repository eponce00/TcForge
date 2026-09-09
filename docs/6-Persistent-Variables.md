# 6 Persistence and restart

Persistent diagnostic data and operating intent have different policies.

| Data | Policy |
|---|---|
| Base active fault | Volatile; detected again from current conditions after restart |
| Last fault and eight-entry history | PERSISTENT; Reset preserves history |
| Alarm latch/ack state | PERSISTENT; alarm configuration and current condition govern evaluation |
| Output saved command | PERSISTENT but never automatically applied by default |
| Output arming, pulse/debounce state, active actuator movement | Volatile |

`restoreCommandOnRestart` defaults FALSE. Default output startup requires a fresh
command and uses `safeOutput` (electrical BOOL) or `safeRaw` (terminal units). Explicit
restoration only works with acceptable quality; invalid startup quality disarms
restoration and requires a new command. ForceSafe and output Reset clear saved
intent. Source locks are application state and must be established on startup.

PERSISTENT declarations do not guarantee survival of sudden power loss. Configure
and validate TwinCAT persistent saving and the target's UPS/shutdown mechanism.
Reset classes, downloads, online changes and persistent layout changes require an
explicit reinitialization policy. Never persist references/pointers to device instances.

Validate default startup and restoration
with the [restart matrix](10-Qualification.md#restart-and-persistence-acceptance-matrix).
The startup-policy unit tests inject saved values; only actual runtime restarts and
power interruption tests establish storage behavior.
