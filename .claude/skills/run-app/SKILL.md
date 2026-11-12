---
name: run-app
description: Start, stop, rebuild, test, inspect or debug the Colorín Colorado Streamlit app (Docker Compose on port 8502) and its optional local GPU engine server (port 8602). Use this whenever the user wants to run the app, see it working, run the tests, check logs, restart after a code change, rebuild after changing requirements.txt or the Dockerfile, or asks why the UI is not loading, why a change does not show up, or why Gemini conversions fail.
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

An optional second service, `local-image` (container `colorin-colorado-local-image`, Compose
profile `gpu`), serves Qwen-Image-2.1 on the NVIDIA GPU at `127.0.0.1:8602` for the **🖥️ Local
GPU** engine. Its weights (~33 GB) live in the shared, external `local-image-models` volume (Once Upon a Time's
GPU server mounts it too; `launch.sh` and `app.sh gpu` create it, on the folder in `LOCAL_IMAGE_MODELS_DIR` when set;
`./launch.sh status` prints where the weights are); it mounts `config/`
read-only and reads only the `LOCAL_IMAGE_*` keys. `./launch.sh` at the repo root checks Docker,
the Gemini credentials and the GPU, creates the Compose override when gcloud credentials exist,
and starts the GPU server only when the machine can run it (`./launch.sh status | stop | logs gpu`).

## Commands

```bash
.claude/skills/run-app/scripts/app.sh status     # container state + health check
.claude/skills/run-app/scripts/app.sh up         # start (builds if needed)
.claude/skills/run-app/scripts/app.sh test       # pytest inside the container (no credentials needed)
.claude/skills/run-app/scripts/app.sh logs 200   # last 200 lines, then follows (Ctrl+C);
                                                 # for a snapshot: docker compose logs --tail 200 app
.claude/skills/run-app/scripts/app.sh restart    # after config/.env changes, or edits made with no tab open
.claude/skills/run-app/scripts/app.sh rebuild    # after requirements.txt / Dockerfile changes
.claude/skills/run-app/scripts/app.sh gpu        # start/rebuild the local GPU engine's server
.claude/skills/run-app/scripts/app.sh gpu-logs   # its logs: download progress, loads, pages
.claude/skills/run-app/scripts/app.sh down
```

`curl -s 127.0.0.1:8602/health` gives the GPU server's `status` (`checking`, `downloading` with
`progress`, `idle`, `loading`, `ready`, `unsupported`, `error`) and the reason in `message`. An
HTTP 507 from `/generate` is a CUDA out-of-memory: another process holds VRAM (`nvidia-smi`), for
example Once Upon a Time's GPU server while it draws.

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
- An AI conversion takes 30–40 s and costs ~$0.14 (a 4K cover image ~$0.25); wait for the "Página convertida" toast. Use the
  free draft for flow checks.

## Debugging checklist

1. **Container restarting**: `docker compose logs --tail 200 app` (`app.sh logs` keeps following);
   an import-time traceback means a broken module.
2. **"Gemini is not configured"**: with `GEMINI_AUTH=adc`, `GOOGLE_CLOUD_PROJECT` is empty; with
   `vertex_key` or `studio_key`, `GEMINI_API_KEY` is. Set it in Settings.
3. **401/403, `DefaultCredentialsError`**: `gcloud auth application-default login` on the host,
   then `app.sh restart`.
4. **404 / model not found**: model name or region; image models need `global`.
5. **"Image generation returned no image"**: safety filter or a bad response; the client retries
   once. Check the prompt from `imaging.build_prompt` before changing anything else.
6. **A click does nothing**: a widget changed identity between runs (value/index or option labels
   from saved data). See "UI rules" in `docs/architecture.md`.
