# 9 HMI integration

Configuration and status structs use OPC UA data attributes with read-only access.
Expose commands through fixed-identity `Operator*` RPC wrappers. Internal program
methods, LockSource, SetBypass and mapping helpers are not RPC-enabled. See [command results](4-RPC-Method-Response.md).

`OPC.UA.DA := '1'` exposes data; `OPC.UA.DA.Access := '1'` makes it read-only;
`OPC.UA.DA.StructuredType := '1'` marks structured data; `TcRpcEnable := '1'` belongs
only on Operator wrappers. Preserve explicit `OPC.UA.DA := '0'` on internal IO and
simulation inputs. Attributes describe symbols, not authentication policy.

Configure authenticated server access and role-based method permissions in the
consuming application. Verify the published symbol/method list against the intended
allowlist after building. Verify RPC admission is separate from command execution in the owning PLC task. A caller
must never be allowed to select PROG identity, change the source lock or bypass
interlocks directly. Required missing conditions are never bypassed by the library.

Render faults from the common header: source, fault string and reason. Last-fault
fields persist after diagnostic reset when storage is configured correctly. Show
admission rejection immediately. After QUEUED, poll OperatorCommandResult with the
same request ID and then observe cyclic state for completion; ACCEPTED is not
completion. Treat lost/evicted results as uncertain and do not replay automatically. Display analog outputInhibited and input quality rather than
presenting an invalid/held value as live measurement. Process-image outputs are not
physical equipment feedback.

The library does not configure an OPC UA server, store login credentials or provide
a user audit service. Server security, role mapping, RPC integration verification and
operator audit requirements are machine/application integration responsibilities
and are part of [qualification](10-Qualification.md).
