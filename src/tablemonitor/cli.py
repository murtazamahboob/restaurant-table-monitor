"""CLI: ``tablemonitor demo`` replays the scripted lunch rush and writes
``outputs/report.json``, ``outputs/report.md`` and ``outputs/floor-map.html``.
``tablemonitor replay`` prints the event timeline; ``tablemonitor dashboard``
writes only the floor map.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .dashboard import render_floor_map
from .replay import run_replay


def _write_report(report: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2))
    m = report["metrics"]
    lines = [
        "# Restaurant Table Monitor — lunch-rush replay",
        "",
        f"Duration: {report['duration_s']:.0f} s, tables: {report['tables']}",
        "",
        "## Measured results",
        "",
        f"- Seatings detected: {m['seated_detection']}",
        f"- Waiter-visit recall: {m['waiter_visit_recall']:.3f} "
        f"(precision {m['waiter_visit_precision']:.3f})",
        f"- POS-cancelled timers: {m['pos_served']}",
        f"- Surface classifier accuracy: {m['surface_accuracy']:.3f} "
        f"over {m['surface_observations']} labelled observations",
        f"- First service: mean {m['first_service_mean_s']} s, "
        f"max {m['first_service_max_s']} s, "
        f"{m['first_service_under_300s']}/{m['tables_served']} under 300 s",
        f"- Unattended alerts: {m['unattended_alerts']}, "
        f"clean-tables-now alerts: {m['clean_tables_now_alerts']}, "
        f"tables cleaned: {m['tables_cleaned']}",
        "",
        "## Final table states",
        "",
    ]
    for tid, state in sorted(report["final_states"].items()):
        lines.append(f"- {tid}: {state}")
    lines += ["", "## Alerts", ""]
    for a in report["alerts"]:
        lines.append(f"- {a['id']} {a['kind']} table {a['table']} "
                     f"{a['severity']} {a['status']}")
    (out_dir / "report.md").write_text("\n".join(lines) + "\n")


def _print_summary(report: dict) -> None:
    m = report["metrics"]
    print(f"Replay: {report['duration_s']:.0f}s, {report['tables']} tables")
    print(f"Seated detection: {m['seated_detection']}")
    print(f"Waiter-visit recall {m['waiter_visit_recall']:.3f}, "
          f"precision {m['waiter_visit_precision']:.3f}")
    print(f"POS-cancelled timers: {m['pos_served']}")
    print(f"Surface accuracy: {m['surface_accuracy']:.3f} "
          f"({m['surface_observations']} labelled observations)")
    print(f"First service: mean {m['first_service_mean_s']}s, "
          f"max {m['first_service_max_s']}s")
    print(f"Unattended alerts: {m['unattended_alerts']}, "
          f"clean-tables-now: {m['clean_tables_now_alerts']}")
    print("Final states: " + ", ".join(
        f"{k}={v}" for k, v in sorted(report["final_states"].items())))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tablemonitor")
    sub = parser.add_subparsers(dest="cmd", required=True)
    demo = sub.add_parser("demo", help="run the lunch-rush replay")
    demo.add_argument("--output-dir", default="outputs")
    replay = sub.add_parser("replay", help="print the event timeline")
    replay.add_argument("--output-dir", default=None)
    dash = sub.add_parser("dashboard", help="write the floor-map HTML")
    dash.add_argument("--output-dir", default="outputs")
    args = parser.parse_args(argv)

    report = run_replay()
    if args.cmd == "replay":
        for ev in report["events"]:
            print(f"{ev['t']:6.0f}s  {ev['table'] or '-':>4}  {ev['event']}"
                  + (f"  {ev.get('source', '')}" if ev.get("source") else ""))
        _print_summary(report)
        return 0
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_report(report, out_dir)
    # Floor map at the end of the replay (final states, open alerts).
    tables = []
    from .replay import build_tables
    for td in build_tables():
        state = report["final_states"][td.table_id]
        tables.append({"id": td.table_id, "x": td.x * 8, "y": td.y * 8,
                       "w": td.w * 8, "h": td.h * 8, "state": state,
                       "capacity": td.capacity, "waiting_s": None})
    (out_dir / "floor-map.html").write_text(
        render_floor_map(tables, report["alerts"]))
    _print_summary(report)
    print(f"Wrote {out_dir / 'report.json'}, {out_dir / 'report.md'}, "
          f"{out_dir / 'floor-map.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
