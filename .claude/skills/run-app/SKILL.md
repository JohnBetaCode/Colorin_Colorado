---
name: run-app
description: Start, stop, rebuild, test, inspect or debug the Colorín Colorado Streamlit app (Docker Compose on port 8502). Use this whenever the user wants to run the app, see it working, run the tests, check logs, restart after a code change, rebuild after changing requirements.txt or the Dockerfile, or asks why the UI is not loading, why a change does not show up, or why Vertex AI conversions fail.
---

# Run the app

One Streamlit process in Docker Compose (service `app`, container `colorin-colorado`), running as
the host user so `books/` and `data/` stay owned by them. Bind mounts:

| Host path | Purpose | Reload behaviour |
|---|---|---|
| `app/` | Python code | Hot reload, but only while a browser tab is connected (see below) |
| `tests/`, `scripts/` | Test suite, prompt spike | Read when run |
| `books/` | Books: JSON, photos, line-art versions, PDF exports | Read on every rerun |
| `data/` | `usage.jsonl` cost log | Read on every rerun |
| `config/` | `.env` settings | Loaded at process start; restart |
| `~/.config/gcloud/application_default_credentials.json` | ADC, read-only | Restart after `gcloud auth ...` |

Only `requirements.txt` and the `Dockerfile` need a rebuild.

## Commands

```bash
.claude/skills/run-app/scripts/app.sh status     # container state + health check
.claude/skills/run-app/scripts/app.sh up         # start (builds if needed)
.claude/skills/run-app/scripts/app.sh test       # pytest inside the container (no credentials needed)
.claude/skills/run-app/scripts/app.sh logs 200   # tail logs
.claude/skills/run-app/scripts/app.sh restart    # after config/.env changes, or edits made with no tab open
.claude/skills/run-app/scripts/app.sh rebuild    # after requirements.txt / Dockerfile changes
.claude/skills/run-app/scripts/app.sh down
```

The UI is http://localhost:8502; health is `GET /_stcore/health`.

## Verifying a change in the browser

Streamlit keeps state per browser session, so `curl` only proves the server is up. Drive it with
Playwright on the system Chrome (`channel="chrome"`), from a throwaway venv outside the repo.
Things that bit before:

- **Stale code.** Streamlit's file watcher belongs to a browser session. Files edited while no
  session was connected are never reloaded: `app.sh restart` before a scripted check.
- Commit text fields with Enter or Tab and wait for the rerun before clicking the next button.
- Labels like "Título" also match "Subtítulo": use `exact=True` or `input[aria-label='Título']:visible`
  (the sidebar's Edit book form has hidden inputs with the same labels).
- An AI conversion takes 30–40 s and costs ~$0.17; wait for the "Página convertida" toast. Use the
  free draft for flow checks.

## Debugging checklist

1. **Container restarting**: `app.sh logs 200`; an import-time traceback means a broken module.
2. **"Google Cloud is not configured"**: `GOOGLE_CLOUD_PROJECT` is empty; set it in Settings.
3. **401/403, `DefaultCredentialsError`**: `gcloud auth application-default login` on the host,
   then `app.sh restart`.
4. **404 / model not found**: model name or region; image models need `global`.
5. **"Image generation returned no image"**: safety filter or a bad response; the client retries
   once. Check the prompt from `imaging.build_prompt` before changing anything else.
6. **A click does nothing**: a widget changed identity between runs (value/index or option labels
   from saved data). See "UI rules" in `docs/architecture.md`.
