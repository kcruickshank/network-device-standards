# Network Device Standards

A single, shared catalogue of standard network devices — their accessories,
links, golden images, lifecycle status, sites and costs — with bills of
materials for pricing standard builds.

The whole app is one self-contained HTML file. It can run three ways:

1. **On its own** — open `app/index.html` in a browser. Data is stored in that
   browser only. Good for a quick look or single-user use.
2. **Shared via the API server** — run the small FastAPI + SQLite service in
   `server/`. Everyone who connects shares one catalogue. (Docker/Kubernetes
   provided.)
3. **Shared via SharePoint** — point the app at SharePoint lists. See
   `docs/SharePoint-Setup-Guide.docx`.

---

## Repository layout

```
.
├── app/
│   └── index.html            The entire application (one file)
├── server/
│   ├── server.py             FastAPI + SQLite backend (shared mode)
│   ├── requirements.txt
│   ├── Dockerfile            Build from the REPO ROOT (see below)
│   ├── .dockerignore
│   └── k8s/
│       ├── nds-api.yaml      Namespace, PVC, Deployment (1 replica), Service
│       └── ingress.yaml      Optional HTTPS ingress
├── docs/
│   ├── NDS-User-Guide.docx        How to use the app
│   └── SharePoint-Setup-Guide.docx
├── docker-compose.yml        One-command run (builds from repo root)
├── .gitignore
└── README.md
```

---

## Quick start

### Option 1 — just open it
Open `app/index.html` in any modern browser. That's it. Data lives in that
browser (Settings → storage shows the mode).

### Option 2 — shared server with Docker (recommended for a team)
From the repository root:
```bash
docker compose up -d --build
```
Then open `http://THIS-MACHINE:8000`. In the app: **Settings → API server
(shared) → Connect**.

- Your data persists in the Docker volume `nds-data` (survives restarts and
  rebuilds).
- To edit the app without rebuilding: change `app/index.html` on disk and
  hard-refresh the browser (the compose file live-mounts it).
- Back up the database:
  ```bash
  docker compose cp nds:/data/nds.db ./nds-backup.db
  ```

### Option 2b — shared server without Docker
```bash
cd server
pip install -r requirements.txt
python server.py
```
Serves on port 8000. The database file `nds.db` is written under `server/`
(or set `NDS_DB_PATH` to another location).

### Option 3 — Kubernetes (single replica)
See `server/k8s/`. Build and push the image, set it in `nds-api.yaml`, then:
```bash
kubectl apply -f server/k8s/nds-api.yaml
```
The Deployment is intentionally **one replica** because the data is a single
SQLite file on a PersistentVolume. Details and the build/push steps are in
`server/README.md`.

> **Building the image:** because the app and server live in separate folders,
> build from the repo root so both are in the build context:
> ```bash
> docker build -f server/Dockerfile -t YOUR_REGISTRY/nds-api:1.0 .
> ```

---

## How the app is structured (for editing)

Everything is in `app/index.html`:
- **Catalog** — card and collapsed views, search, and filters (device type,
  use case, and lifecycle: End of Sale / End of Life / End of Support).
- **Actions** — add/edit devices, accessories, links, features, licensing,
  golden images, sites, unit-cost review, and the types & groups taxonomy.
- **Bills of materials** — costed device + accessory lists with two Excel
  exports (quotation and price-estimate).
- **Settings** — storage mode (browser / SharePoint / API server), currency
  (EUR/GBP with conversion), an admin password that gates deletes and heading
  edits, branding, and JSON export/import.

The app talks to whichever storage backend is selected through a small
"storage adapter" layer, so the same file works in all three modes.

---

## Data & backups

- **API/Docker mode:** all data is the single file `nds.db` (in the volume, or
  under `server/`). Copy it to back up.
- **Any mode:** **Settings → Export JSON** produces a portable backup of the
  whole catalogue that can be re-imported.
- Never commit `nds.db` — it's covered by `.gitignore`.

---

## Notes on security

The in-app admin password is a **UI guardrail** — it stops people deleting or
editing protected items through the interface. It is not a substitute for
access control at the storage layer. For real protection, use SharePoint list
permissions, or put the API server behind a reverse proxy with authentication
(e.g. Entra ID SSO) and HTTPS. See `server/README.md` for pointers.
