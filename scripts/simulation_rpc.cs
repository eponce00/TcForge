// Persistent, deliberately narrow ADS RPC transport for the isolated simulation FB.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Web.Script.Serialization;
using TwinCAT.Ads;
using TwinCAT;
using TwinCAT.Ads.TypeSystem;
using TwinCAT.TypeSystem;

class SimulationRpc
{
    static int Main(string[] args)
    {
        if (args.Length != 2) return 2;
        Environment.SetEnvironmentVariable("PATH", @"C:\Program Files (x86)\Beckhoff\TwinCAT\Common64;" + Environment.GetEnvironmentVariable("PATH"));
        var json = new JavaScriptSerializer();
        using (var client = new AdsClient())
        {
            try
            {
                client.Connect(args[0], int.Parse(args[1]));
                client.Timeout = 2000;
                object identity = client.InvokeRpcMethod("MAIN.simulation", "Identity", new object[0]);
                if (Convert.ToString(identity) != "TcForge.DiscreteAssembly/2")
                    throw new Exception("Unexpected simulation identity");
                // Resolve once per transport lifetime. InvokeRpcMethod resolves and
                // releases a method handle on every call, adding two ADS round trips.
                // This fixed ABI belongs to DiscreteAssembly/2; incompatible PLC
                // method signatures must change that identity before deployment.
                using (var methods = new SimulationMethods(client))
                {
                Console.WriteLine(json.Serialize(new { ready = true, identity = identity }));
                string line;
                while ((line = Console.ReadLine()) != null)
                {
                    try
                    {
                        string[] fields = line.Split(' ');
                        object value;
                        switch (fields[0])
                        {
                            case "snapshot":
                                value = methods.Snapshot(); break;
                            case "claim": case "release":
                                value = methods.Call(fields[0] == "claim" ? "Claim" : "Release",
                                    ulong.Parse(fields[1]), ulong.Parse(fields[2])); break;
                            case "exchange":
                                value = methods.Call("Exchange", new object[] {
                                    ulong.Parse(fields[1]), ulong.Parse(fields[2]), ulong.Parse(fields[3]), ulong.Parse(fields[4]),
                                    fields[5] == "1", fields[6] == "1", fields[7] == "1", fields[8] == "1",
                                    fields[9] == "1", fields[10] == "1", fields[11] == "1", fields[12] == "1",
                                    short.Parse(fields[13]), short.Parse(fields[14]), fields[15] == "1", fields[16] == "1",
                                    ushort.Parse(fields[17]) }); break;
                            default: throw new Exception("Unknown simulation operation");
                        }
                        Console.WriteLine(json.Serialize(new { value = value }));
                    }
                    catch (Exception e)
                    {
                        Console.WriteLine(json.Serialize(new { error = e.Message }));
                        // No handle reacquisition or command replay after uncertainty.
                        // A new transport must identify the runtime and reconcile state.
                        return 1;
                    }
                }
                return 0;
                }
            }
            catch (Exception e) { Console.Error.WriteLine(e); return 1; }
        }
    }
}

sealed class SimulationMethods : IDisposable
{
    readonly AdsClient client;
    readonly Dictionary<string, uint> handles = new Dictionary<string, uint>();
    public SimulationMethods(AdsClient client)
    {
        this.client = client;
        try
        {
            var loader = SymbolLoaderFactory.Create(client, new SymbolLoaderSettings(SymbolsLoadMode.Flat));
            var rpc = (IRpcCallableInstance)loader.Symbols["MAIN.simulation"];
            CheckSignature(rpc, "Snapshot", "STRING(255)", 256, new string[0], new string[0]);
            foreach (string method in new[] { "Claim", "Release" })
                CheckSignature(rpc, method, "DINT", 4, new[] { "client", "expectedBoot" }, new[] { "ULINT", "ULINT" });
            CheckSignature(rpc, "Exchange", "DINT", 4,
                new[] { "client", "expectedBoot", "frame", "outputFrame", "clampAdvanced", "clampRetracted",
                    "pressAdvanced", "pressRetracted", "ejectorAdvanced", "ejectorRetracted", "partPresent",
                    "dischargeClear", "pressureRaw", "heightRaw", "shutdownConfirmed", "qualityGood", "requestedCommand" },
                new[] { "ULINT", "ULINT", "ULINT", "ULINT", "BOOL", "BOOL", "BOOL", "BOOL", "BOOL", "BOOL",
                    "BOOL", "BOOL", "INT", "INT", "BOOL", "BOOL", "UINT" });
            foreach (string name in new[] { "Snapshot", "Claim", "Release", "Exchange" })
                handles.Add(name, client.CreateVariableHandle("MAIN.simulation#" + name));
        }
        catch { Dispose(); throw; }
    }
    static void CheckSignature(IRpcCallableInstance rpc, string name, string returnType,
        int returnSize, string[] names, string[] types)
    {
        var method = rpc.RpcMethods.Single(m => m.Name == name);
        if (method.ReturnType != returnType || method.ReturnTypeSize != returnSize ||
            method.Parameters.Count != names.Length || method.OutParameters.Count != 0)
            throw new InvalidDataException("Unexpected simulation RPC signature: " + name);
        for (int i = 0; i < names.Length; i++)
        {
            var p = method.Parameters[i];
            int size = types[i] == "ULINT" ? 8 : types[i] == "BOOL" ? 1 : 2;
            if (p.Name != names[i] || p.TypeName != types[i] || p.Size != size || !p.IsInput() || p.IsOutput())
                throw new InvalidDataException("Unexpected simulation RPC parameter: " + name + "." + p.Name);
        }
    }
    byte[] Invoke(string method, byte[] input, int size)
    {
        var output = new byte[size];
        // ADS SymbolValueByHandle ReadWrite invokes an RPC method handle.
        int read = client.ReadWrite(0xF005, handles[method], output.AsMemory(), input.AsMemory());
        if (read != size) throw new InvalidDataException("Unexpected RPC response length");
        return output;
    }
    public string Snapshot()
    {
        var data = Invoke("Snapshot", new byte[0], 256); // STRING(255), including NUL.
        int end = Array.IndexOf(data, (byte)0);
        if (end < 0) throw new InvalidDataException("Unterminated RPC snapshot");
        return Encoding.ASCII.GetString(data, 0, end);
    }
    public int Call(string method, params object[] arguments)
    {
        using (var buffer = new MemoryStream())
        {
            using (var writer = new BinaryWriter(buffer, Encoding.ASCII, true))
                foreach (object value in arguments)
                {
                    if (value is ulong) writer.Write((ulong)value);
                    else if (value is ushort) writer.Write((ushort)value);
                    else if (value is short) writer.Write((short)value);
                    else if (value is bool) writer.Write((bool)value);
                    else throw new InvalidDataException("Unsupported simulation RPC argument type");
                }
            using (var reply = new BinaryReader(new MemoryStream(Invoke(method, buffer.ToArray(), 4))))
                return reply.ReadInt32();
        }
    }
    public void Dispose()
    {
        foreach (uint handle in handles.Values)
            try { client.DeleteVariableHandle(handle); } catch { /* Connection closure also releases handles. */ }
        handles.Clear();
    }
}
