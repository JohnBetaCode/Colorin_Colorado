# Setup

## What you need

- Docker with Compose.
- Access to Gemini, in one of three ways (**⚙️ Settings → Authentication**, or `GEMINI_AUTH`):

  | Method | `GEMINI_AUTH` | What you need |
  |---|---|---|
  | Google Cloud | `adc` (default) | A project with the **Vertex AI API** enabled, permission to call it (`roles/aiplatform.user`), and the gcloud CLI logged in on the host: `gcloud auth application-default login`. The same project as Once Upon a Time works. |
  | Vertex AI API key | `vertex_key` | An API key for Vertex AI (Google Cloud console → APIs & Services → Credentials). No project ID or gcloud needed. |
  | Google AI Studio API key | `studio_key` | A key from [Google AI Studio](https://aistudio.google.com/apikey) (the Gemini Developer API). Model names there may differ, for example with a `-preview` suffix. |

Without any of them the app still runs: the free draft engine converts photos offline.

## Run

```bash
git clone git@github.com:JohnBetaCode/Colorin_Colorado.git
cd Colorin_Colorado
cp config/.env.example config/.env   # then set the project or an API key, or do it from the app
# Only with Google Cloud credentials (GEMINI_AUTH=adc): mount them into the container
cp docker-compose.override.example.yml docker-compose.override.yml
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
| `GEMINI_AUTH` | `adc` | How to reach Gemini: `adc`, `vertex_key` or `studio_key` (see above). |
| `GEMINI_API_KEY` | — | The API key, for `vertex_key` and `studio_key`. |
| `GOOGLE_CLOUD_PROJECT` | — | GCP project ID. Required with `adc`. |
| `GOOGLE_CLOUD_LOCATION` | `global` | Region of the text model. |
| `GEMINI_IMAGE_LOCATION` | `global` | Region of the image model (image models are usually served from `global`). |
| `GEMINI_TEXT_MODEL` | `gemini-3.8-flash` | Text model (connection test; caption suggestions later). |
| `GEMINI_IMAGE_MODEL` | `gemini-3-pro-image` | Image model that draws the coloring pages. |
| `UI_LANGUAGE` | `es` | App language, `es` or `en`. Also switchable from the sidebar. |

Credentials are never copied into the image: `.dockerignore` keeps `config/.env` (project ID, API
key) and the user data out of it, and Compose mounts `config/` at run time. The gcloud credentials
file is mounted only by `docker-compose.override.yml`, which you copy from
`docker-compose.override.example.yml` when you use `adc` (the `run-app` script does it for you
when the file exists). Both `config/.env` and the override are git-ignored.

## Data

| Path | Contents |
|---|---|
| `books/<slug>/` | Each book: `book.json`, `pages.json`, uploaded photos, every coloring-page version, cover images, PDF exports and KDP covers. |
| `data/usage.jsonl` | One line per Gemini call with tokens and estimated cost. |

Both are bind-mounted and git-ignored. Back up `books/` to keep your books.

## Tests

```bash
docker compose run --rm --no-deps app python -m pytest -p no:cacheprovider tests
```

The suite needs no credentials: it uses synthetic images and the draft engine. The export tests
read the PDF back and check that every coloring page is pure black and white.

## Troubleshooting

- **"Gemini is not configured"**: in **⚙️ Settings**, set the project ID (Google Cloud) or the API
  key (the two API key methods).
- **`DefaultCredentialsError` with `adc` although gcloud is logged in**: the credentials are not
  mounted. Copy `docker-compose.override.example.yml` to `docker-compose.override.yml` and
  `docker compose up -d`.
- **An empty folder named `application_default_credentials.json`** in `~/.config/gcloud` (left by an
  older version of this setup, which mounted the file even when it did not exist): delete it before
  running `gcloud auth application-default login`.
- **401/403 or `DefaultCredentialsError`**: run `gcloud auth application-default login` on the
  host, then `docker compose restart app`.
- **404 / model not found**: wrong model name or region; image models need `global`.
- **"Image generation returned no image"**: usually the safety filter. The client retries once;
  try again, crop differently or add instructions.
- **A code change does not show up**: Streamlit reloads changed modules only while a browser tab
  is connected. If you edited files with no tab open, `docker compose restart app`.
- **Changes to `requirements.txt` or the `Dockerfile`**: `docker compose up -d --build`.
