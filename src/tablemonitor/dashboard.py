"""Live floor-map dashboard (static HTML + SVG, no server needed) and
analytics over a replay: first-service times, unattended counts, turnover
and dirty-table minutes.
"""

from __future__ import annotations

import html
import statistics

STATE_COLOURS = {
    "EMPTY_CLEAN": "#2e9e5b",
    "OCCUPIED_WAITING": "#e8a13a",
    "ALERT_UNATTENDED": "#d64545",
    "OCCUPIED_SERVED": "#3a7bd5",
    "EMPTY_DIRTY": "#8a5a2b",
}


def render_floor_map(tables: list[dict], alerts: list[dict],
                     title: str = "Restaurant Table Monitor — live floor map") -> str:
    """``tables``: [{id, x, y, w, h, state, capacity, waiting_s}]."""
    cells = []
    for tb in tables:
        colour = STATE_COLOURS.get(tb["state"], "#888888")
        label = f'T{tb["id"]} · {tb["state"].replace("_", " ")}'
        sub = f'cap {tb.get("capacity", 4)}'
        if tb.get("waiting_s") is not None:
            sub += f' · waiting {int(tb["waiting_s"])}s'
        cells.append(
            f'<g><rect x="{tb["x"]}" y="{tb["y"]}" width="{tb["w"]}" '
            f'height="{tb["h"]}" rx="10" fill="{colour}" stroke="#222" '
            f'stroke-width="2"/><text x="{tb["x"] + tb["w"] / 2}" '
            f'y="{tb["y"] + tb["h"] / 2 - 4}" text-anchor="middle" '
            f'fill="white" font-size="13" font-weight="bold">'
            f'{html.escape(label)}</text><text x="{tb["x"] + tb["w"] / 2}" '
            f'y="{tb["y"] + tb["h"] / 2 + 14}" text-anchor="middle" '
            f'fill="white" font-size="11">{html.escape(sub)}</text></g>')
    alert_rows = "".join(
        f'<li><b>{html.escape(a["kind"])}</b> — table '
        f'{html.escape(str(a.get("table")))} · {html.escape(a["severity"])} · '
        f'{html.escape(a["status"])}</li>' for a in alerts)
    legend = "".join(
        f'<span style="background:{c};color:#fff;padding:2px 8px;'
        f'border-radius:4px;margin-right:6px">{s.replace("_", " ")}</span>'
        for s, c in STATE_COLOURS.items())
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>{html.escape(title)}</title></head>
<body style="font-family:sans-serif;max-width:900px;margin:24px auto">
<h1>{html.escape(title)}</h1><p>{legend}</p>
<svg width="860" height="420" style="border:1px solid #ccc;border-radius:8px">
{''.join(cells)}</svg>
<h2>Alerts</h2><ul>{alert_rows or '<li>No open alerts.</li>'}</ul>
<p><small>Privacy: no video is stored; faces are blurred before any frame
is analysed. Generated offline by restaurant-table-monitor.</small></p>
</body></html>"""


def analytics(events: list[dict], alerts: list[dict]) -> dict:
    """Summarise a replay: service times, unattended, turnover, cleaning."""
    served = [e["first_service_time"] for e in events
              if e["event"] in ("served", "alert_closed")
              and e.get("first_service_time") is not None]
    seatings = len([e for e in events if e["event"] == "seated"])
    unattended = len([a for a in alerts if a["kind"] == "UNATTENDED_TABLE"])
    return {
        "seatings": seatings,
        "tables_served": len(served),
        "first_service_mean_s": round(statistics.mean(served), 1) if served else None,
        "first_service_max_s": round(max(served), 1) if served else None,
        "first_service_under_300s": sum(1 for s in served if s < 300),
        "unattended_alerts": unattended,
        "clean_tables_now_alerts": len(
            [a for a in alerts if a["kind"] == "CLEAN_TABLES_NOW"]),
        "tables_cleaned": len([e for e in events if e["event"] == "cleaned"]),
    }
