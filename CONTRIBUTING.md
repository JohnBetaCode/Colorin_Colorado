# Contributing

Thanks for wanting to help. Bug reports, ideas, fixes, translations and new styles are all
welcome.

## Before you start

- **Bugs**: open an issue with what you did, what you expected and what happened, the book's
  settings (style, age group, background), and the last lines of the log
  (`docker compose logs --tail 200 app`). Never attach personal photos, `config/.env` or API keys.
- **Bigger changes** (a new view, a new style, a dependency): open an issue first, so we agree on
  the approach before you spend time on it.

## Set up

You need Docker with Compose. Most work needs no Google Cloud account: the free draft engine
converts photos offline, and the tests never call Gemini.

```bash
git clone git@github.com:JohnBetaCode/Colorin_Colorado.git
cd Colorin_Colorado
cp config/.env.example config/.env
docker compose up -d --build        # http://localhost:8502
```

The [setup guide](docs/setup.md) covers Gemini access, configuration and troubleshooting, and the
[architecture](docs/architecture.md) explains the modules, the data layout and the pipelines.

## Run the tests

```bash
docker compose run --rm --no-deps app python -m pytest -p no:cacheprovider tests
```

They run in the container (Streamlit and OpenCV are not needed on the host), use synthetic images,
and take a few seconds. Add a test with every change in `app/core/`.

## How the code is written

- **English** for code, comments, prompts, docs and commit messages. Every user-facing string goes
  through `app/core/i18n.py` with both a Spanish and an English text; `tests/test_i18n.py` checks it.
- **Business logic in `app/core/`**, which never imports Streamlit; `app/ui/` only calls it and
  renders. Widgets fed from saved data are seeded with `ui.common.seed` (see "UI rules" in the
  architecture doc for why).
- **Every Gemini call goes through `app/core/gemini.py`** and records its usage; book work runs
  inside `usage.book_context(book.id)`.
- **Coloring pages are pure black and white**: every one goes through `lineart.clean`, and line art
  is never JPEG-encoded. Versions are never overwritten.
- **Examples are place-neutral**: no country or city in the README, docs, UI placeholders or tests.
- **Prompt changes** (styles, ages, backgrounds) are checked on real photos with
  `scripts/spike.py` and recorded in `docs/spike.md`. A new style or age group needs an entry in
  every per-age table (`lineart`, `imaging.AGE_PROMPTS`, `extras`).
- **User data stays out of git**: `books/`, `data/`, `spike/`, `config/.env` and
  `docker-compose.override.yml`. No real project IDs or API keys in examples.

`CLAUDE.md` has the full list of conventions.

## Pull requests

1. Branch from `main` and keep the change focused.
2. Write commit messages that say what changed and why.
3. Make sure the tests pass, and update the docs (README, `docs/`) when behavior changes.
4. For UI changes, add a screenshot to the pull request.
5. If you ran paid Gemini calls to test, say roughly how much, and add a row to
   `docs/development-cost.md`.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
