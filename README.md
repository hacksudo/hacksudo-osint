# OSINT — HACKSUDO

A web-based, evidence-led public-source intelligence workspace for authorized research. HACKSUDO aggregates public search results, profiles, articles, news, images and videos, then organizes them into reviewable cases with explainable relevance scoring and analyst-controlled false-positive exclusion.

> Public search hits are leads, not proof of identity. Use HACKSUDO only for lawful, authorized public-source research.

## Features

- Web, social, blog/news, image and video discovery
- Optional Google Programmable Search, Brave Search, OpenAI web search and YouTube Data API providers
- Works with no API keys using its fallback public collector
- Platform-specific social identity pivots
- Controlled second-hop public-page crawling
- Evidence relevance signals and false-positive exclusion
- Evidence Profile workspace
- Branded HTML, PDF and Excel exports
- Responsive cyber-operations UI
- Docker and Docker Compose deployment
- Health-check endpoint at `/health`

## Quick start with Docker

```bash
git clone https://github.com/hacksudo/hacksudo-osint.git
cd hacksudo-osint

docker build -t hacksudo/osint:latest .
docker run --rm -p 8080:8080 hacksudo/osint:latest
```

Open `http://localhost:8080`.

No API key is required to start. Optional providers improve coverage.

## Docker Compose

```bash
cp .env.example .env
# Add only the provider credentials you want to use.
docker compose up -d --build
docker compose logs -f
```

Stop it with:

```bash
docker compose down
```

## Optional API providers

| Provider | Environment variable | Purpose |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | Additional public web discovery |
| Brave Search | `BRAVE_SEARCH_API_KEY` | Web, news, image and video indexes |
| Google Programmable Search | `GOOGLE_CSE_API_KEY` + `GOOGLE_CSE_CX` | Google-backed web and image results |
| YouTube Data API v3 | `YOUTUBE_API_KEY` | Dedicated YouTube video discovery |

The dashboard also contains setup links under **API SOURCES**.

Never put production credentials in the Dockerfile, source code, Git history, or a public Docker image. `.env` is ignored by Git and Docker build context.

## Local Python installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:8080`.

## Build and publish to Docker Hub

Sign in:

```bash
docker login
```

Build using your Docker Hub namespace:

```bash
docker build -t hacksudo/hacksudo-osint:latest .
docker tag hacksudo/hacksudo-osint:latest hacksudo/hacksudo-osint:12.0
```

Test before publishing:

```bash
docker run --rm -p 8080:8080 hacksudo/hacksudo-osint:latest
```

Push:

```bash
docker push hacksudo/hacksudo-osint:latest
docker push hacksudo/hacksudo-osint:12.0
```

Users can then run:

```bash
docker run -d \
  --name hacksudo-osint \
  -p 8080:8080 \
  hacksudo/hacksudo-osint:latest
```

With optional API credentials:

```bash
docker run -d \
  --name hacksudo-osint \
  -p 8080:8080 \
  -e BRAVE_SEARCH_API_KEY="$BRAVE_SEARCH_API_KEY" \
  -e GOOGLE_CSE_API_KEY="$GOOGLE_CSE_API_KEY" \
  -e GOOGLE_CSE_CX="$GOOGLE_CSE_CX" \
  -e YOUTUBE_API_KEY="$YOUTUBE_API_KEY" \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  hacksudo/hacksudo-osint:latest
```

Recommended repository topics:

`osint` `cybersecurity` `public-source-intelligence` `python` `flask` `docker` `investigation` `search`

## Production notes

The container runs Flask behind Gunicorn as a non-root user. The default port is `8080`.

Useful environment variables:

```text
HACKSUDO_PORT=8080
WEB_CONCURRENCY=2
GUNICORN_THREADS=4
```

For internet-facing deployment, place the container behind a reverse proxy such as Nginx, Caddy, Cloudflare Tunnel, or your hosting provider's HTTPS ingress.

### Secrets in containers

Desktop OS keyrings are not guaranteed inside headless containers. For Docker deployments, inject secrets at runtime through environment variables, Docker/Swarm secrets, Kubernetes Secrets, or your cloud secret manager. Never bake them into the image.

## Evidence exports

From the **Evidence Profile** tab you can export:

- **HTML** — self-contained dark HACKSUDO report suitable for offline viewing.
- **PDF** — print-friendly investigation report with case summary, entity assessment, relevance values, source URLs and numbered evidence.
- **Excel** — structured evidence suitable for analyst review and filtering.

Evidence manually excluded as a false positive is left out of generated profile exports.

## Project structure

```text
.
├── app.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .dockerignore
├── templates/
│   └── index.html
├── static/
│   ├── app.js
│   └── style.css
└── data/
```

## Responsible use

HACKSUDO is intended for lawful public-source research, security investigations, training, brand/project research and other authorized OSINT workflows. Do not use it to bypass access controls, obtain private data, or treat automated correlation as definitive identity proof.

## Author / links

**Vishal Waghmare — HACKSUDO**

- Website: https://hacksudo.com
- LinkedIn: https://www.linkedin.com/in/realvilu
- Instagram: https://www.instagram.com/realvilu/

## License

Add the license you want to use before publishing publicly (for example MIT, Apache-2.0, GPL-3.0, or a custom license).

© HACKSUDO · All rights reserved · Vishal Waghmare
