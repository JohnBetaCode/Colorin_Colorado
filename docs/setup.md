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

Optionally, if this computer has an NVIDIA GPU with 24 GB of VRAM or more: the **local GPU**
engine, which draws coloring pages on it with an open model at no cost per image and starts with
the app (see [Local GPU engine](#local-gpu-engine)).

Optionally, another engine for coloring pages: your own **Stable Diffusion** server
([stable-diffusion.cpp](https://github.com/leejet/stable-diffusion.cpp)'s `sd-server` with
FLUX.1 Kontext), set in **⚙️ Settings → Stable Diffusion**. It draws pages only, slower (1–2
minutes each, one at a time) and with no cost per image; captions, translations and covers still
need Gemini. Check the model's license (FLUX.1 Kontext [dev] is non-commercial) and the server's
rules before selling pages made with it.

## Run

```bash
git clone https://github.com/JohnBetaCode/Colorin_Colorado.git
cd Colorin_Colorado
./launch.sh
```

`launch.sh` checks Docker and how the app will reach Gemini (and creates
`docker-compose.override.yml` to mount your gcloud credentials when you use them), then starts
the app. When the computer has an NVIDIA GPU that can run the local image model, it starts the
local GPU engine too; otherwise it says why. Set the project or an API key in **⚙️ Settings**, or
in `config/.env` (copied from `config/.env.example`).

| Command | What it does |
|---|---|
| `./launch.sh` | Start the app, plus the local GPU engine when this computer can run it |
| `./launch.sh cloud` | Start the app only |
| `./launch.sh gpu` | Start the app and the local GPU engine, or explain why the GPU cannot run it |
| `./launch.sh status` | Containers, health and the local GPU server's state (including download progress) |
| `./launch.sh stop` | Stop everything; books, settings and downloaded models are kept |
| `./launch.sh logs [app\|gpu]` | Follow the logs of the app or of the GPU server |

The plain Compose equivalents are `docker compose up -d --build` (after copying the override
when you use gcloud credentials) and, with the GPU engine, `docker volume create
local-image-models` (once) and `docker compose --profile gpu up -d --build`.

Open http://localhost:8502. Once Upon a Time uses port 8501, so both can run at the same time.

The app only answers on this computer. To open it from a phone or another computer on your
network, start it with `COLORIN_BIND=0.0.0.0 docker compose up -d`; the app has no login, so anyone
on that network can then use it, see the books and spend your Gemini credit.

The container runs as your host user (`UID`/`GID`, default 1000), so `books/` and `data/` stay
owned by you. If your user id is not 1000, start it with `UID=$(id -u) GID=$(id -g) docker
compose up -d`.

## Local GPU engine

The **🖥️ Local GPU** engine draws coloring pages with
[Qwen-Image-2.1](https://huggingface.co/Qwen/Qwen-Image-2.1), an open model that takes the photo
as its reference, on this computer's NVIDIA GPU. It runs in its own container (Compose profile
`gpu`), gets the same coloring-page prompt as Gemini, and every page goes through the same cleanup.

| Requirement | Detail |
|---|---|
| GPU | NVIDIA with at least 24 GB of VRAM; 32 GB recommended. Tested on an RTX 5090 |
| Driver and Docker | NVIDIA driver 570 or newer and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) |
| Memory | About 40 GB of RAM; the loaded model holds about 25 GB |
| Disk | About 45 GB free where Docker stores its data: 33 GB of weights and the server image |

**License.** Qwen-Image-2.1 is under the Qwen Research License, for research and evaluation.
Pages drawn with it are fine to try styles and for books you will not sell; to sell them you need
a commercial agreement with Alibaba. The KDP panel warns about every page whose selected version
was drawn with it.

**Start it.** `./launch.sh` starts it automatically when the requirements are met; `./launch.sh gpu`
insists and tells you what is missing. The first start builds the server image and downloads the
33 GB of weights once, a few minutes on a fast connection; `./launch.sh status` and
**⚙️ Settings → Local GPU** show the progress. The weights survive rebuilds and are shared with
Once Upon a Time's GPU server; see [where the models live](#where-the-models-live) below.

**Use it.** In the workbench, **🖥️ Local GPU** converts the page; **Convert all** has the same
option. The button is enabled while the server is ready. On an RTX 5090:

| Page size (`LOCAL_IMAGE_PAGE_SIZE`) | Time per page | What it gives |
|---|---|---|
| `1k` (default) | 30–60 s | Cleaner, continuous strokes |
| `2k` | about 105 s | The model's native size: keeps more background in busy scenes, but strokes come out more broken |

It does best with clear subjects (a bird, a face, a pet) and less well than Gemini with very
detailed scenes; [the spike](spike.md#local-gpu-2026-11-12) has the comparison. After 20 idle
minutes the server unloads the model to free its RAM, and the next page loads it again.

Once Upon a Time ships the same server on port 8600; Colorín Colorado's listens on
`127.0.0.1:8602`, so both can run and they share the downloaded weights, though two loaded
models need about 50 GB of RAM.

### Where the models live

The weights go in one Docker volume, `local-image-models`, shared by
every project that runs this server (Once Upon a Time and Colorín Colorado), so each model
downloads once per computer. By default Docker keeps it in its own storage
(`/var/lib/docker/volumes/local-image-models` on Linux). To keep the models in a folder of your
choice, on another disk or somewhere you back up, set `LOCAL_IMAGE_MODELS_DIR` in `config/.env`
(or in your environment) before the first `./launch.sh`; the launcher creates the volume on that
folder. The first project that creates the volume decides where it lives, so set the same value in
every project; if they disagree, `launch.sh` says where the weights really are. `./launch.sh status`
shows the location. The volume is external to Compose, so `docker compose down -v` never deletes it.

To move weights you already downloaded into a folder:

```bash
./launch.sh stop                                    # in every project that runs the GPU server
mkdir -p /data/models
docker run --rm -v local-image-models:/src -v /data/models:/dst alpine cp -a /src/. /dst/
docker volume rm local-image-models
echo "LOCAL_IMAGE_MODELS_DIR=/data/models" >> config/.env   # in every project
./launch.sh gpu
```

The server runs as root in its container, so the files it writes in that folder belong to root.
To free the space, stop every GPU server, run `docker volume rm local-image-models`, and delete the
folder if you set one.

## Branches

| Branch | What it has | Docker image |
|---|---|---|
| `main` | Everything: AI and draft engines, mystery mosaics (one pen included) with **automatic background removal** (IS-Net, see [below](#background-removal)), page templates, PDF and Amazon KDP files. | About 0.9 GB |
| `SAM` | Background removal for mosaics with **SAM2** instead, where you click points on the photo to say what is subject and what is background: more control on hard photos. PyTorch (CPU) is installed in the image and the SAM2 model (about 320 MB, public, no account needed) downloads by itself the first time into `models/`. It may lag behind `main` in other features. | About 2.3 GB |

Use `main` unless you need to point at the subject by hand. To switch, change the branch and
rebuild the image, since the two have different requirements:

```bash
git switch SAM        # or: git switch main
mkdir -p books data models
docker compose up -d --build
```

Books are shared between branches. A mosaic page saved with "Remove the background" on `SAM`
also removes it on `main`, with IS-Net (the points clicked on `SAM` are ignored there).

## Configuration

Settings live in `config/.env` (git-ignored). The **⚙️ Settings** panel on the home page edits
them and can test the connection: for Gemini, **Save & test** sends one cheap text request; for
Stable Diffusion it reads the model's state without waking it up.

| Variable | Default | What it is |
|---|---|---|
| `GEMINI_AUTH` | `adc` | How to reach Gemini: `adc`, `vertex_key` or `studio_key` (see above). |
| `GEMINI_API_KEY` | — | The API key, for `vertex_key` and `studio_key`. |
| `GOOGLE_CLOUD_PROJECT` | — | GCP project ID. Required with `adc`. |
| `GOOGLE_CLOUD_LOCATION` | `global` | Region of the text model. |
| `GEMINI_IMAGE_LOCATION` | `global` | Region of the image model (image models are usually served from `global`). |
| `GEMINI_TEXT_MODEL` | `gemini-3.8-flash` | Text model (connection test; caption suggestions later). |
| `GEMINI_IMAGE_MODEL` | `gemini-3-pro-image` | Image model that draws the coloring pages. |
| `LOCAL_IMAGE_URL` | `http://local-image:8000` | The local GPU server, as the app sees it. Without Docker: `http://localhost:8602`. |
| `LOCAL_IMAGE_PAGE_SIZE` | `1k` | Local GPU page size: `1k` (30–60 s, cleaner strokes) or `2k` (native, ~105 s). |
| `STABLE_DIFFUSION_URL` | — | Stable Diffusion server, e.g. `http://192.168.1.20:8081`. Empty: the engine is off. |
| `STABLE_DIFFUSION_STEPS` | `12` | Sampling steps, 4–30. 8–12 looks almost like the server's default 20 in half the time. |
| `STABLE_DIFFUSION_SIZE` | `768` | Long side of the photo sent to the server, 512–1024 px. 768 takes 1–1.5 minutes; 1024 nearly twice as long. |
| `UI_LANGUAGE` | `es` | App language, `es` or `en`. Also switchable from the sidebar. |

The local GPU server reads its own settings from the same file, and only the keys that start
with `LOCAL_IMAGE_` (Compose mounts `config/` read-only; the API key never reaches that
container). Restart it after changing them: `docker compose --profile gpu up -d local-image`.

| Variable | Default | What it is |
|---|---|---|
| `LOCAL_IMAGE_MODEL` | `Qwen/Qwen-Image-2.1` | Hugging Face model id. `Qwen/Qwen-Image-2.1-Turbo` exists but is untested here; pair it with 8 steps. |
| `LOCAL_IMAGE_STEPS` | `40` | Sampling steps per page. |
| `LOCAL_IMAGE_IDLE_MINUTES` | `20` | Unload the model after this idle time; `0` keeps it loaded. |
| `LOCAL_IMAGE_PRELOAD` | `1` | Load the model at start-up (`1`) or on the first page (`0`). |
| `LOCAL_IMAGE_CFG` | `1.0` | Guidance; above 1 enables a negative prompt at ~1.6x the time (the app sends none). |
| `LOCAL_IMAGE_OFFLOAD` | `model` | `none` keeps the whole model on the GPU (needs ~40 GB of VRAM). |
| `LOCAL_IMAGE_MIN_VRAM_GB` | `24` | The server refuses to start on GPUs with less VRAM. |
| `LOCAL_IMAGE_MODELS_DIR` | Docker's storage | Folder for the shared weights; read by `launch.sh` when it creates the `local-image-models` volume. Same value in every project. |

The saved API key is never sent to the browser: the Settings field stays empty, shows the key's last
four characters, and keeps the saved key unless you type a new one (**Forget the saved API key**
removes it).

Credentials are never copied into the image: `.dockerignore` keeps `config/.env` (project ID, API
key) and the user data out of it, and Compose mounts `config/` at run time. The gcloud credentials
file is mounted only by `docker-compose.override.yml`, which you copy from
`docker-compose.override.example.yml` when you use `adc` (the `run-app` script does it for you
when the file exists). Both `config/.env` and the override are git-ignored.

## Background removal

Mosaics can remove the photo's background with **IS-Net** (Apache-2.0), a small model that runs on
the CPU with ONNX Runtime, offline and free. It downloads by itself the first time it is used
(about 180 MB) into `models/`, which Compose mounts, so rebuilds keep it; the app checks the
file's SHA-256 before using it. To download it in advance:

```bash
mkdir -p models && curl -L -o models/isnet-general-use.onnx \
  https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx
```

## Data

| Path | Contents |
|---|---|
| `books/<slug>/` | Each book: `book.json`, `pages.json`, uploaded photos, every coloring-page version, cover images, PDF exports and KDP covers. |
| `data/usage.jsonl` | One line per Gemini call with tokens and estimated cost, and one per local GPU or Stable Diffusion page (no cost). |
| `models/` | Downloaded models (background removal). Safe to delete: they download again. |

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
- **Stable Diffusion fails or times out**: the server must be reachable from the container (same
  network or VPN). After 10 idle minutes it unloads the model, so the next page takes 10–30 s
  more; when other people use it, pages wait in its queue. **Save & test** shows the model's state.
- **The 🖥️ Local GPU button is disabled**: the server is not running or not ready. `./launch.sh
  status` says which; **⚙️ Settings → Local GPU** shows the same, in the app's language.
- **`launch.sh`: "Docker cannot use the GPU"**: install the NVIDIA Container Toolkit, run
  `sudo nvidia-ctk runtime configure --runtime=docker`, then `sudo systemctl restart docker`.
- **"needs at least 24 GB" (unsupported)**: this GPU is too small for the model; use Gemini or
  Stable Diffusion.
- **"the GPU ran out of memory"**: another program (a game, another model, Once Upon a Time's
  GPU server while it draws) is using the GPU. Wait or close it, and try again.
- **A code change does not show up**: Streamlit reloads changed modules only while a browser tab
  is connected. If you edited files with no tab open, `docker compose restart app`.
- **Changes to `requirements.txt` or the `Dockerfile`**: `docker compose up -d --build`.
