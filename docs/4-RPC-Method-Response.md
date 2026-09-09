# 4 Command results and RPC

Program commands return their validation result synchronously. Remote Operator
methods return `QUEUED` when the mailbox admits a command. Query
`OperatorCommandResult(requestId)` for the owning task's result. `ACCEPTED` means
the device accepted intent, not physical completion; observe cyclic status and
physical feedback afterward. Sequence intent can still be cancelled by current
conditions or a higher priority program command.

| Value | Meaning |
|---|---|
| 0 | Device accepted command intent |
| 1 | Queued; owner has not dispatched yet |
| 2 | Cancelled before dispatch |
| 11 | Operator source locked |
| 12 | Owning cyclic task has not initialized the mailbox |
| 13 | Conflicting cyclic task detected; remote commands blocked |
| 20 | Wrong state or incompatible pending device request |
| 21 | Device fault blocks ordinary command |
| 22 | Mailbox occupied, locked or cancelling normal commands |
| 23 | Already at target |
| 30 | Invalid parameter/requester, including zero request ID |
| 31 | Bypass not configured as allowed |
| 34 | Request unknown or its result no longer retained |
| 35 | Request ID already retained; no resubmission occurred |
| 50 | Permissive not met |
| 51 | Interlock or pending output fallback prevents command |
| 100 | Unknown rejection |

All Operator command methods require a caller-supplied `requestId : ULINT`.
`OperatorSetValue` additionally accepts `rValue : REAL`. Allocate nonzero IDs unique
across clients and PLC restarts. Only the last eight admitted requests are retained
per instance, including pending and cancelled results. A duplicate ID is rejected
while retained. The mailbox is volatile: restart clears pending commands and result
history. Result eviction or restart can produce UNKNOWN; neither proves that a
command did not execute. Do not automatically replay commands after a connection
loss, timeout or unknown result. Reconcile machine state and require a fresh
operator decision. There is no durable or exactly-once delivery guarantee.

An immediate BUSY submission admits nothing; the HMI may retry with bounded delay
while the operator's intent is still current. A BUSY result query should be polled
again. Stop/Abort can replace lower priority pending requests, but lock contention
can still return BUSY. Remote control is not an emergency-stop transport.

Applicable blocks expose OperatorHome, OperatorStart, OperatorStop, OperatorAbort,
OperatorPause, OperatorProceed, OperatorRetry, OperatorReset, OperatorAdvance,
OperatorRetract, OperatorSetOn, OperatorSetOff, OperatorSetValue, OperatorForceSafe
and OperatorAck. Internal methods, LockSource, SetBypass, mapping and step mutation
are not RPC-enabled. Inherited Reset dispatches the concrete device override.

ForceSafe applies configured electrical/raw fallback on the next cyclic call,
independent of debounce/inversion. SetOff means logical off and is not an
electrical fallback for an inverted output. State-machine Reset requires the
stopped recovery conditions; use Stop or Abort to stop.
