# Development cost

What building this repository has cost in Gemini calls: every conversion, cover, banner and test
made while developing it. From `data/usage.jsonl`, at public list prices; Google billing is the
source of truth.

| Stage | Date | Calls | Images | Tokens | Cost |
|---|---|---|---|---|---|
| Line-art spike and MVP checks (39 spike images, 1 UI run) | 2026-10-30 | 40 | 40 | 95,815 | $6.80 |
| Amazon KDP: three AI covers, the image-size check, two README banners | 2026-10-31 | 6 | 6 | 25,875 | $1.26 |
| Connect-the-dots check, three new styles, three translations, one listing | 2026-10-31 | 8 | 4 | 15,665 | $0.58 |
| **Total** | | **54** | **50** | **137,355** | **≈ $8.64** |

- Entries before 2026-10-31 priced the model's thinking tokens at the image rate ($120/M instead
  of $12/M), so the first row is a little high.
- The demo book used for the README images is logged as the book `readme-demo`; calls outside any
  book (the image-size check, the banners) as "no book".
- Not included: the AI coding assistant used to write the code, and hosting (the app runs
  locally).

The **📊 Usage & costs** panel on the home page shows the same log, live, by book and by
operation. Add a row here when a development round spends money.
