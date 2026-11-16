"""Summarize AI usage and estimated cost from data/usage.jsonl (read-only).

Usage:
    python3 report.py                     # totals + breakdown by book, model and day
    python3 report.py --by operation      # one breakdown: book, model, day or operation
    python3 report.py --book <id|slug|title|none>   # one book ("none": calls made outside a book)
    python3 report.py --days 7            # only the last 7 days
    python3 report.py --since 2026-11-01  # only from that UTC date on
    python3 report.py --tail 10           # also print the last 10 raw entries
    python3 report.py --json              # machine-readable output

Each line of the log is one call recorded by app/core/usage.py:
    ts, book (a book *id*, or a label like "spike", or null), operation, model,
    input_tokens, output_tokens (thinking included), thinking_tokens (newer entries only),
    images, web_search, cost_usd (estimated when the call was made, from PRICING).

Reuses app.core.usage (stdlib only) so the numbers match the app's usage panel. Book titles
come from books/*/book.json, read directly so the script runs with the host python3
(no Streamlit, pydantic or OpenCV needed). The log and the books are never written.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True  # leave no host-Python caches in app/ (the container uses its own)

from app.core import usage  # noqa: E402

# Models logged on purpose without a PRICING entry because they cost nothing per call:
# the author's own Stable Diffusion server (app/core/stable_diffusion.py, MODEL).
FREE_UNPRICED = {"stable-diffusion"}
NO_BOOK = "—"  # how usage.breakdown labels entries without a book


def book_titles() -> dict[str, tuple[str, str]]:
    """Book id -> (slug, title) for every book currently under books/."""
    titles = {}
    for path in sorted((ROOT / "books").glob("*/book.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("id"):
            titles[data["id"]] = (data.get("slug", path.parent.name), data.get("title", ""))
    return titles


def book_label(book_id: str, titles: dict[str, tuple[str, str]]) -> str:
    if book_id == NO_BOOK:
        return "(no book: settings, tests)"
    if book_id in titles:
        slug, title = titles[book_id]
        return f"{title} [{slug}]"
    if len(book_id) == 32 and all(c in "0123456789abcdef" for c in book_id):
        return f"(deleted book {book_id[:8]})"
    return book_id  # a label such as "spike" (scripts/spike.py)


def match_book(selector: str, titles: dict[str, tuple[str, str]]) -> set[str | None]:
    """Book ids a --book argument refers to: an id, a slug, part of a title, or 'none'."""
    if selector.lower() in ("none", "-", NO_BOOK):
        return {None, ""}
    ids = {i for i, (slug, title) in titles.items() if selector in (i, slug) or selector.lower() in title.lower()}
    return ids or {selector}  # a deleted book's id or a label like "spike"


def day(entry: dict) -> str:
    return (entry.get("ts") or "")[:10] or NO_BOOK


def fmt_table(rows: list[dict]) -> str:
    if not rows:
        return "(no entries)"
    cols = list(rows[0])
    numeric = {c for c in cols if all(isinstance(r[c], (int, float)) for r in rows)}
    widths = {c: max(len(str(c)), *(len(fmt_cell(r[c])) for r in rows)) for c in cols}

    def cell(c: str, v) -> str:
        return fmt_cell(v).rjust(widths[c]) if c in numeric else fmt_cell(v).ljust(widths[c])

    line = " | ".join(str(c).ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    body = [" | ".join(cell(c, r[c]) for c in cols) for r in rows]
    return "\n".join([line, sep, *body])


def fmt_cell(v) -> str:
    if isinstance(v, float):
        return f"{v:.4f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def grouped(entries: list[dict], key: str, titles: dict[str, tuple[str, str]]) -> list[dict]:
    if key == "day":
        rows = usage.breakdown([{**e, "day": day(e)} for e in entries], "day")
        return sorted(rows, key=lambda r: r["day"])  # chronological, not by cost
    rows = usage.breakdown(entries, key)
    if key == "book":
        for row in rows:
            row["book"] = book_label(row["book"], titles)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--book", help="book id, slug, part of its title, or 'none'")
    ap.add_argument("--days", type=float, help="only the last N days")
    ap.add_argument("--since", help="only entries from this UTC date on (YYYY-MM-DD)")
    ap.add_argument("--by", choices=["book", "model", "day", "operation"], help="a single breakdown")
    ap.add_argument("--tail", type=int, default=0, help="also print the last N raw entries")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    titles = book_titles()
    entries = usage.load_entries()
    if args.days is not None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()
        entries = [e for e in entries if e.get("ts", "") >= cutoff]
    if args.since:
        entries = [e for e in entries if e.get("ts", "") >= args.since]
    if args.book:
        wanted = match_book(args.book, titles)
        entries = [e for e in entries if e.get("book") in wanted]

    totals = usage.summarize(entries)
    totals["thinking_tokens"] = sum(e.get("thinking_tokens", 0) for e in entries)
    paid_images = [e for e in entries if e.get("images") and e.get("cost_usd", 0) > 0]
    n_paid = sum(e["images"] for e in paid_images)
    per_paid_image = sum(e["cost_usd"] for e in paid_images) / n_paid if n_paid else 0.0
    free_images = totals["images"] - n_paid
    unpriced = sorted({e.get("model", "?") for e in entries}
                      - set(usage.PRICING) - FREE_UNPRICED)
    keys = [args.by] if args.by else ["book", "model", "day"]

    if args.json:
        print(json.dumps({
            "file": str(usage.USAGE_FILE),
            "totals": totals,
            "paid_images": n_paid,
            "free_images": free_images,
            "avg_cost_per_paid_image_usd": round(per_paid_image, 4),
            "unpriced_models": unpriced,
            **{f"by_{k}": grouped(entries, k, titles) for k in keys},
            "tail": entries[-args.tail:] if args.tail else [],
        }, indent=2, ensure_ascii=False))
        return

    print(f"Usage log: {usage.USAGE_FILE}")
    if entries:
        print(f"From {entries[0].get('ts', '?')[:16]} to {entries[-1].get('ts', '?')[:16]} UTC")
    print(f"Calls: {totals['calls']}   Input tokens: {totals['input_tokens']:,}   "
          f"Output tokens: {totals['output_tokens']:,} (thinking {totals['thinking_tokens']:,})   "
          f"Images: {totals['images']}   Est. cost: ${totals['cost_usd']:.2f}")
    if totals["images"]:
        print(f"Images: {n_paid} paid at ~${per_paid_image:.3f} each, {free_images} free "
              "(local GPU / Stable Diffusion)")
    if unpriced:
        print(f"WARNING: no price in app/core/usage.py PRICING for: {', '.join(unpriced)} "
              "(their cost is counted as $0).")
    for key in keys:
        print(f"\nBy {key}{' (UTC)' if key == 'day' else ''}:")
        print(fmt_table(grouped(entries, key, titles)))
    if args.tail:
        print(f"\nLast {args.tail} entries:")
        for e in entries[-args.tail:]:
            print(json.dumps(e, ensure_ascii=False))
    print("\nEstimates from list prices at call time; the Google Cloud billing console is the source of truth.")


if __name__ == "__main__":
    main()
