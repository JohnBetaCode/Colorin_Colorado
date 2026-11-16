---
name: usage-report
description: Report Colorín Colorado's AI token usage and estimated USD cost from data/usage.jsonl, per book, per model, per day or per operation, and keep the PRICING table in app/core/usage.py current. Use this whenever the user asks how much a book or its coloring pages cost, how many images or API calls were made, what the spike or the cover art cost, wants to compare spend between books, models or days, asks whether the local GPU engine saved money, changes GEMINI_TEXT_MODEL / GEMINI_IMAGE_MODEL / LOCAL_IMAGE_MODEL, or asks about Gemini pricing.
---

# Usage and cost reporting

Every AI call appends one JSON line to `data/usage.jsonl` (`app/core/usage.py`, `record`):

| Field | Meaning |
|---|---|
| `ts` | UTC timestamp (ISO 8601) |
| `book` | the book's **id** (`book.json` → `id`, not the slug), set by `usage.book_context`; a label such as `spike` (`scripts/spike.py`) or `readme-demo`; or `null` for calls made outside a book (connection tests from Settings) |
| `operation` | `image_generation`, `extraction`, `web_research`, `connection_test` (and occasional ad-hoc labels) |
| `model` | `gemini-3-pro-image`, `gemini-3.8-flash`, ...; local GPU images as `<model>-local` (`qwen-image-2.1-local`); Stable Diffusion as `stable-diffusion` |
| `input_tokens`, `output_tokens` | `output_tokens` already includes the thinking tokens |
| `thinking_tokens` | only on entries written after it was added; missing means 0 |
| `images` | images returned by the call (coloring pages, cover art) |
| `web_search` | grounded call, plus `WEB_SEARCH_COST_PER_REQUEST` |
| `cost_usd` | estimate computed **when the call was made** from `PRICING` |

Callers: `gemini.py` (every Gemini call), `local_image.py` and `stable_diffusion.py` (one image,
$0). Book work is wrapped in `usage.book_context(book.id)` by `imaging`, `captions` and
`cover_art`. The home page's "📊 Usage & costs" panel and the book sidebar read the same file.

The figures are estimates from list prices: the Google Cloud billing console is the source of
truth; say so whenever you report a number.

## Reporting

`data/usage.jsonl` is user data: read it, never edit, truncate or "fix" it. The script only reads it
and `books/*/book.json` (for titles), and runs with the host `python3` (it imports only
`app.core.usage`, which is stdlib; no container needed):

```bash
S=.claude/skills/usage-report/scripts/report.py
python3 $S                           # totals + by book, by model, by day (UTC)
python3 $S --by operation            # one breakdown: book | model | day | operation
python3 $S --book <id|slug|title>    # one book; part of the title works; --book spike, --book none
python3 $S --days 7                  # last 7 days;  --since 2026-11-01 for a UTC date
python3 $S --tail 5                  # plus the last raw entries
python3 $S --json                    # for further processing
```

Book labels: a current book shows as `Title [slug]`; a 32-hex id that matches no folder under
`books/` shows as `(deleted book xxxxxxxx)`; `(no book: settings, tests)` are calls made outside
`book_context`. The `Images` line splits paid images (average cost each) from free ones (local GPU,
Stable Diffusion).

When answering a cost question, lead with the number asked for, then the breakdown that explains
it (for example: "40 Gemini pages at about $0.17 each are $6.80 of the $8.64; the 3 local GPU pages
were free").

## What drives cost

| Work | Model | Typical cost |
|---|---|---|
| Coloring page, Gemini (1K/2K) | image model | ~1,100–1,500 output tokens, ~$0.14–0.17 (thinking tokens at the text rate) |
| Cover art, 4K | image model | ~2,000 output tokens, ~$0.25 |
| Coloring page, local GPU / Stable Diffusion | `<model>-local`, `stable-diffusion` | $0 (electricity only) |
| Free draft, mystery mosaic, extras, PDF | none | not logged: $0 |
| Caption translation, Amazon listing | text model | tokens only, under a cent |
| Connection test | text model | negligible |

**Convert all** runs one image call per page (three Gemini calls at a time), and every
**Otra con Gemini** / regenerate is another full image call; deleted versions stay in the log.

## Keeping prices current

`PRICING` only knows the models listed in it; an unknown model is costed at $0 and the report
prints `WARNING: no price ... for: <model>` (`stable-diffusion` is $0 on purpose and is not flagged).
When a model id changes, follow CLAUDE.md: for `GEMINI_*`, update `config/.env.example`, the
defaults in `app/core/config.py`, `PRICING` (with current Vertex AI list prices from the official
pricing page, not from memory; keep the comments on intro pricing windows, e.g. gemini-3.8-flash
doubles from 2027) and the table in `docs/setup.md`. For `LOCAL_IMAGE_MODEL`, add `<model>-local` at
$0. Then run the report and confirm no warning remains.

`cost_usd` is frozen at call time: a price change does not re-cost old entries. To compare with
current prices, recompute from the tokens and `PRICING` instead of editing the log.
