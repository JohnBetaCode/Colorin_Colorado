# Setup

## What you need

- Docker with Compose.
- A Google Cloud project with the **Vertex AI API** enabled, and permission to call it
  (`roles/aiplatform.user`). The same project as Once Upon a Time works.
- The gcloud CLI on the host, logged in for Application Default Credentials:

  ```bash
  gcloud auth application-default login
  ```

Without Google Cloud the app still runs: the free draft engine converts photos offline.

## Run

```bash
git clone git@github.com:JohnBetaCode/Colorin_Colorado.git
cd Colorin_Colorado
cp config/.env.example config/.env   # then set GOOGLE_CLOUD_PROJECT, or do it from the app
docker compose up -d --build
```

Open http://localhost:8502. Once Upon a Time uses port 8501, so both can run at the same time.

The container runs as your host user (`UID`/`GID`, default 1000), so `books/` and `data/` stay
owned by you. If your user id is not 1000, start it with `UID=$(id -u) GID=$(id -g) docker
compose up -d`.

## Configuration

Settings live in `config/.env` (git-ignored). The **⚙️ Settings** panel on the home page edits
them and can test the connection; **Save & test** sends one cheap text request.

| Variable | Default | What it is |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | — | GCP project ID. Required for AI conversions. |
| `GOOGLE_CLOUD_LOCATION` | `global` | Region of the text model. |
| `GEMINI_IMAGE_LOCATION` | `global` | Region of the image model (image models are usually served from `global`). |
| `GEMINI_TEXT_MODEL` | `gemini-3.8-flash` | Text model (connection test; caption suggestions later). |
| `GEMINI_IMAGE_MODEL` | `gemini-3-pro-image` | Image model that draws the coloring pages. |
| `UI_LANGUAGE` | `es` | App language, `es` or `en`. Also switchable from the sidebar. |

Credentials are never copied into the image: Compose mounts
`~/.config/gcloud/application_default_credentials.json` read-only.

## Data

| Path | Contents |
|---|---|
| `books/<slug>/` | Each book: `book.json`, `pages.json`, uploaded photos, every coloring-page version, PDF exports. |
| `data/usage.jsonl` | One line per Gemini call with tokens and estimated cost. |

Both are bind-mounted and git-ignored. Back up `books/` to keep your books.

## Tests

```bash
docker compose run --rm --no-deps app python -m pytest -p no:cacheprovider tests
```

The suite needs no credentials: it uses synthetic images and the draft engine. The export tests
read the PDF back and check that every coloring page is pure black and white.

## Troubleshooting

- **"Google Cloud is not configured"**: set the project ID in **⚙️ Settings**.
- **401/403 or `DefaultCredentialsError`**: run `gcloud auth application-default login` on the
  host, then `docker compose restart app`.
- **404 / model not found**: wrong model name or region; image models need `global`.
- **"Image generation returned no image"**: usually the safety filter. The client retries once;
  try again, crop differently or add instructions.
- **A code change does not show up**: Streamlit reloads changed modules only while a browser tab
  is connected. If you edited files with no tab open, `docker compose restart app`.
- **Changes to `requirements.txt` or the `Dockerfile`**: `docker compose up -d --build`.
