"""Read-only snapshot timing for an already running isolated simulation PLC."""
import argparse
import json
from pathlib import Path
import statistics
import time

from tcforge_sim.live import RpcTransport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    parser.add_argument('--port', type=int, default=854)
    parser.add_argument('--transport', required=True, type=Path)
    parser.add_argument('--samples', type=int, default=30)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if not 1 <= args.samples <= 1000:
        parser.error('samples must be 1..1000')
    start = time.perf_counter()
    rpc = RpcTransport(args.transport.resolve(strict=True), args.target, args.port)
    startup = time.perf_counter() - start
    timings = []
    try:
        for _ in range(args.samples):
            start = time.perf_counter()
            rpc.snapshot()
            timings.append((time.perf_counter() - start) * 1000)
    finally:
        rpc.close()
    result = dict(target=args.target, port=args.port, startup_seconds=startup,
                  samples_ms=timings, median_ms=statistics.median(timings),
                  maximum_ms=max(timings), scope='Read-only snapshots; no cyclic IO qualification')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'samples_ms'}))


if __name__ == '__main__':
    main()
