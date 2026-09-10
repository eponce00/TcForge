// Test-only ADS qualification against MAIN.rpcOutput in TcForge.Tests.
// Does not discover or control production device symbols.
using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using TwinCAT.Ads;

class VerifyOperatorRpc
{
    static string target;
    static int port;
    static T Read<T>(AdsClient c, string path)
    {
        uint h = c.CreateVariableHandle(path);
        try { return (T)c.ReadAny(h, typeof(T)); }
        finally { c.DeleteVariableHandle(h); }
    }
    static void Pump(AdsClient c, bool enabled)
    {
        uint h = c.CreateVariableHandle("MAIN.enableRpcPump");
        try { c.WriteAny(h, enabled); }
        finally { c.DeleteVariableHandle(h); }
        Thread.Sleep(100);
    }
    static int Call(AdsClient c, string method, ulong id, string path = "MAIN.rpcOutput")
    {
        return Convert.ToInt32(c.InvokeRpcMethod(path, method, new object[] { id }));
    }
    static void Equal(int expected, int actual, string message)
    {
        if (expected != actual) throw new Exception(message + ": expected " + expected + ", got " + actual);
        Console.WriteLine("PASS " + message);
    }
    static int Result(AdsClient c, ulong id)
    {
        for (int i = 0; i < 100; i++)
        {
            int result = Call(c, "OperatorCommandResult", id);
            if (result != 1 && result != 22) return result;
            Thread.Sleep(10);
        }
        throw new Exception("Command result timed out");
    }
    static void WaitForCancellationBarrier(AdsClient c)
    {
        // ForceSafe completes before the next owner scan reconciles its barrier.
        // Observe that scan before pausing the fixture or issuing fresh work.
        for (int i = 0; i < 100; i++)
        {
            if (!Read<bool>(c, "MAIN.rpcOutput._operatorMailbox._cancelNormal")) return;
            Thread.Sleep(10);
        }
        throw new Exception("Owner did not reconcile cancellation barrier");
    }
    static int Main(string[] args)
    {
        if (args.Length != 2) { Console.Error.WriteLine("Usage: verify_operator_rpc <test AMS Net ID> <test PLC port>"); return 2; }
        target = args[0]; port = int.Parse(args[1]);
        Environment.SetEnvironmentVariable("PATH", @"C:\Program Files (x86)\Beckhoff\TwinCAT\Common64;" + Environment.GetEnvironmentVariable("PATH"));
        using (var c = new AdsClient())
        {
            try
            {
                c.Connect(target, port);
                int owner = Read<int>(c, "MAIN.rpcContext.ownerTask");
                int rpc = Convert.ToInt32(c.InvokeRpcMethod("MAIN.rpcContext", "ReadContext", new object[0]));
                Console.WriteLine("Cyclic context=" + owner + "; RPC context=" + rpc);
                if (owner <= 0) throw new Exception("Test task has not run");
                ulong id = (ulong)DateTime.UtcNow.Ticks;
                Equal(12, Call(c, "OperatorSetOn", id, "MAIN.rpcUninitialized"), "Uninitialized owner rejects RPC");
                Pump(c, true);
                Equal(1, Call(c, "OperatorForceSafe", id++), "Initial safe command queued");
                Equal(0, Result(c, id - 1), "Initial safe command executed");
                WaitForCancellationBarrier(c);
                Pump(c, false);
                ulong on = id++;
                Equal(1, Call(c, "OperatorSetOn", on), "Remote normal command queued");
                Equal(0, Read<bool>(c, "MAIN.rpcOutput.outSignal") ? 1 : 0, "RPC does not mutate output while owner is paused");
                Equal(1, Call(c, "OperatorCommandResult", on), "Paused owner retains queued result");
                Equal(35, Call(c, "OperatorSetOn", on), "Duplicate request rejected");
                ulong safe = id++;
                Equal(1, Call(c, "OperatorForceSafe", safe), "ForceSafe supersedes pending SetOn");
                Equal(2, Call(c, "OperatorCommandResult", on), "Superseded request records cancellation");
                Equal(22, Call(c, "OperatorSetOn", id++), "Normal request cannot replace ForceSafe");
                Pump(c, true);
                Equal(0, Result(c, safe), "Owner executes ForceSafe");
                WaitForCancellationBarrier(c);
                Equal(owner, Read<int>(c, "MAIN.rpcOutput._operatorMailbox.lastExecutionTask"), "Dispatch runs in owning cyclic task");
                ulong fresh = id++;
                Equal(1, Call(c, "OperatorSetOn", fresh), "Fresh command queued");
                Equal(0, Result(c, fresh), "Fresh command accepted by owner");
                Equal(1, Read<bool>(c, "MAIN.rpcOutput.outSignal") ? 1 : 0, "Owner applies fresh output command");
                Pump(c, false);
                ulong first = id;
                var submissions = Enumerable.Range(0, 16).Select(n => Task.Run(() =>
                {
                    using (var concurrent = new AdsClient())
                    {
                        concurrent.Connect(target, port);
                        return Call(concurrent, "OperatorSetOff", first + (ulong)n);
                    }
                })).ToArray();
                Task.WaitAll(submissions);
                Equal(1, submissions.Count(t => t.Result == 1), "Concurrent clients admit exactly one pending command");
                Equal(15, submissions.Count(t => t.Result == 22), "Remaining concurrent clients receive bounded BUSY");
                Pump(c, true);
                int winner = Array.FindIndex(submissions, t => t.Result == 1);
                Equal(0, Result(c, first + (ulong)winner), "Concurrent winner executes once");
                Equal(0, Read<bool>(c, "MAIN.rpcOutput.outSignal") ? 1 : 0, "Concurrent stop leaves test output off");
                Console.WriteLine("ADS RPC qualification passed. OPC UA server/security and restart qualification remain separate.");
                return 0;
            }
            catch (Exception e) { Console.Error.WriteLine(e); return 1; }
            finally
            {
                if (c.IsConnected)
                {
                    try
                    {
                        Pump(c, true);
                        ulong cleanup = (ulong)DateTime.UtcNow.Ticks;
                        if (Call(c, "OperatorForceSafe", cleanup) == 1) Result(c, cleanup);
                    }
                    catch (Exception e) { Console.Error.WriteLine("Test fixture cleanup: " + e.Message); }
                }
            }
        }
    }
}
