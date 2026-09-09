# 3 Command source control

Program code calls methods such as `Start(eRequester := E_Requester.PROG)` from
the owning cyclic task. Remote callers submit `OperatorStart(requestId := ...)`.
The wrapper only admits a request to a bounded mailbox. The device cyclic body
consumes it and calls the command with fixed `E_Requester.OPERATOR` identity.
External callers cannot supply requester identity. `LockSource(TRUE)` rejects
ordinary operator commands while allowing program commands. LockSource is not RPC.

Every requester-bearing command validates the requester enum before rejecting or
changing device state, including Reset, Ack, Stop, Abort, ForceSafe and SetOff.
Normal commands also validate source locks and faults. Recovery commands retain
their explicit exceptions: Retry permits designated step faults; Stop, Abort,
ForceSafe and logical SetOff bypass ordinary source/fault restrictions. SetOff
still respects a pending ForceSafe, and output inversion still applies.

Each instance has one pending remote command. Priority is Abort/ForceSafe, then
Stop/SetOff, then Reset, then ordinary commands. Higher priority cancels the pending
request; equal or lower priority returns BUSY. Accepted program shutdown/recovery
commands cancel pending normal remote work before consumption. Rejected commands
do not clear queued intent. Urgent commands are operational controls, not a
replacement for an independent safety system.

The mailbox binds to the first positive cyclic task index that consumes it. RPC
context cannot consume it. A different consuming task latches an ownership conflict
and blocks further remote admission. This does not make other device operations
safe to share between tasks: all program methods and cyclic calls have one owner.
A nonblocking TestAndSet lock protects admission, results and owner dispatch;
contending calls return BUSY. There are no spin waits or unbounded queues.

Authentication, certificates, method permissions and user audit are application
responsibilities. Source labels are not user identities. Raw ADS access can write
PLC memory and must be restricted independently of the RPC contract. See
[command results](4-RPC-Method-Response.md) and [qualification](10-Qualification.md).

The implementation uses Beckhoff's [TestAndSet primitive](https://infosys.beckhoff.com/content/1033/tc3_plc_intro/31023115.html)
and [GETCURTASKINDEXEX](https://infosys.beckhoff.com/content/1033/tcplclib_tc2_system/31018507.html).
The local ADS probe observed RPC context 0 and cyclic context 1. A real-time RPC
context alone therefore does not establish cyclic ownership; see Beckhoff's
[RPC processing context](https://infosys.beckhoff.com/content/1033/tf6100_tc3_opcua_server/15617760267.html).
