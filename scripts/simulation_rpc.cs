// Persistent, deliberately narrow ADS RPC transport for the isolated simulation FB.
using System;
using System.Web.Script.Serialization;
using TwinCAT.Ads;

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
                if (Convert.ToString(identity) != "TcForge.DiscreteSimulation/1")
                    throw new Exception("Unexpected simulation identity");
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
                                value = client.InvokeRpcMethod("MAIN.simulation", "Snapshot", new object[0]); break;
                            case "claim": case "release":
                                value = client.InvokeRpcMethod("MAIN.simulation", fields[0] == "claim" ? "Claim" : "Release",
                                    new object[] { ulong.Parse(fields[1]), ulong.Parse(fields[2]) }); break;
                            case "exchange":
                                value = client.InvokeRpcMethod("MAIN.simulation", "Exchange", new object[] {
                                    ulong.Parse(fields[1]), ulong.Parse(fields[2]), ulong.Parse(fields[3]), ulong.Parse(fields[4]),
                                    fields[5] == "1", fields[6] == "1", fields[7] == "1", fields[8] == "1", ushort.Parse(fields[9]) }); break;
                            default: throw new Exception("Unknown simulation operation");
                        }
                        Console.WriteLine(json.Serialize(new { value = value }));
                    }
                    catch (Exception e) { Console.WriteLine(json.Serialize(new { error = e.Message })); }
                }
                return 0;
            }
            catch (Exception e) { Console.Error.WriteLine(e); return 1; }
        }
    }
}
