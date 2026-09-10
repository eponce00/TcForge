# 6 Persistence and restart

Persistent diagnostic data and operating intent have different policies.

| Data | Policy |
|---|---|
| Base active fault | Volatile; detected again from current conditions after restart |
| Last fault and eight-entry history | PERSISTENT; Reset preserves history |
| Alarm latch/ack state | PERSISTENT; alarm configuration and current condition govern evaluation |
| Output saved command and validity marker | PERSISTENT but never automatically applied by default |
| Output arming, pulse/debounce state, active actuator movement | Volatile |

`restoreCommandOnRestart` defaults FALSE. Default output startup requires a fresh
command and uses `safeOutput` (electrical BOOL) or `safeRaw` (terminal units). Explicit
restoration requires a saved command explicitly marked valid by an accepted command,
plus acceptable quality. An absent image or invalidated command remains inhibited even
when restoration is enabled: an inverted DO does not treat default FALSE as SetOff,
and an AO uses `safeRaw` rather than a default zero command. Invalid startup quality disarms
restoration and requires a new command. ForceSafe, output Reset, and behavior-affecting
configuration changes invalidate saved intent. Accepted FALSE/zero commands remain valid
intent; validity is separate from the stored value. Source locks are application state and must be established on startup.

Output restoration also requires `_AppInfo.BootDataLoaded = TRUE` and
`_AppInfo.OldBootData = FALSE`. At startup, an untrusted image invalidates old saved
intent even when restoration is disabled; later image trust cannot revive it.
A fresh command accepted in the current execution is independent of image provenance.
A RAM-preserving reset after a fresh download can therefore remain inhibited when
`BootDataLoaded` is FALSE, even if its saved-command marker survives. This is intentional.
The flags describe runtime loading, not whether the latest command reached durable
storage. Beckhoff recommends evaluating both [persistent loading flags](https://infosys.beckhoff.com/content/1033/tc3_plc_intro/3434442123.html).

PERSISTENT declarations do not guarantee survival of sudden power loss. Configure
and validate TwinCAT persistent saving and the target's UPS/shutdown mechanism.
Reset classes, downloads, online changes and persistent layout changes require an
explicit reinitialization policy. Never persist references/pointers to device instances.

Validate default startup and restoration
with the [restart matrix](10-Qualification.md#restart-and-persistence-acceptance-matrix).
The startup-policy unit tests inject saved values; only actual runtime restarts and
power interruption tests establish storage behavior.
