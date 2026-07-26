# Network Device Standards — shared API server

This is a small server that lets several people share **one** Network Device
Standards catalogue, as an alternative to SharePoint. Everyone connects to it
from the app's **Settings → API server (shared)** option.

It is deliberately tiny: one Python file, one database file. No SharePoint, no
cloud account needed.

---

## What's in this folder

| File         | What it is                                                        |
|--------------|-------------------------------------------------------------------|
| `server.py`  | The server. Run this.                                             |
| `index.html` | **You add this** — a copy of your app file, renamed to this name. |
| `nds.db`     | Created automatically on first run. **This is your data.**        |

---

## Setup (one time)

1. **Install Python 3.9 or newer** on the machine that will host the server.
   Check with: `python --version`

2. **Install the two libraries it needs.** In a terminal/command prompt:
   ```
   pip install fastapi "uvicorn[standard]"
   ```

3. **Put your app file next to `server.py` and name it `index.html`.**
   Take the `network-device-standards.html` file and copy it into this folder
   as `index.html`. This lets the server hand the app straight to people's
   browsers, so they only need a web address — nothing to install.

---

## Running it

### Quick start (testing, or a very small team on one machine)
```
python server.py
```
Then open **http://localhost:8000** in a browser on that machine.

### For your team to reach it
Other people need the machine's name or IP address, and the server must be
reachable on your network. Start it the same way, then share:
```
http://THAT-MACHINE-NAME:8000
```
(replace `THAT-MACHINE-NAME` with the host's name or IP, e.g.
`http://10.20.1.50:8000`).

If port 8000 is in use or blocked, you can run it on another port:
```
uvicorn server:app --host 0.0.0.0 --port 8080
```

---

## Connecting the app to it

1. Open the app (the web address above).
2. Go to **Settings**.
3. Choose **API server (shared)**.
4. The address is usually pre-filled. If not, type the server address
   (e.g. `http://10.20.1.50:8000`).
5. Click **Connect & verify**.

That's it — from now on everyone connected to the same server shares one
catalogue. If two people edit the same device at once, the app warns the second
person and reloads the latest version instead of silently overwriting, exactly
like the SharePoint mode.

**The SharePoint option is still there** — switching to the API server doesn't
remove it. If you later get SharePoint working you can switch back in Settings.

---

## Backups

Your entire catalogue is the single file **`nds.db`**. To back up, just copy it
somewhere safe (do this on a schedule if the data matters). To restore, put the
copy back. You can also use the app's **Settings → Export JSON** as a second,
human-portable backup.

---

## Running with Docker (recommended for servers)

Docker bundles Python, the libraries, and the server into one image, so the
host only needs Docker installed — nothing else. This is the tidiest way to run
it on a server or VM.

**One time:** put your app file in this folder as `index.html` (same as above).

**Build and run with Docker Compose (easiest):**
```
docker compose up -d --build
```
That builds the image, starts it in the background, and keeps your data in a
named volume (`nds-data`) so it survives restarts and updates. The app is then
at `http://THIS-MACHINE:8000`.

To stop / start / update:
```
docker compose down              # stop
docker compose up -d             # start again
docker compose up -d --build     # rebuild after you drop in a new index.html
```

**Or plain Docker (no compose):**
```
docker build -f server/Dockerfile -t nds-api .   # from repo root
docker run -d --name nds-api -p 8000:8000 -v nds-data:/data --restart unless-stopped nds-api
```

**Where the data lives:** inside the container the database is at `/data/nds.db`,
kept in the `nds-data` volume. Back it up with:
```
docker run --rm -v nds-data:/data -v "$PWD":/backup busybox cp /data/nds.db /backup/nds-backup.db
```
or simply copy the volume through your normal Docker/host backup process. (You
can also use the app's **Settings → Export JSON** as a portable backup.)

**Moving to another host:** copy the `nds.db` out of the volume (command above),
stand the container up on the new host, and copy the file back into its volume.

---

## Running on Kubernetes (single replica)

If you already run a Kubernetes cluster, the manifests in the `k8s/` folder
deploy this as a single, self-healing pod with its data on a PersistentVolume.

> **Why one replica?** The catalogue lives in one SQLite file. Running several
> replicas would let pods corrupt that shared file. The Deployment is pinned to
> `replicas: 1` with a `Recreate` strategy on purpose. You still get Kubernetes'
> self-healing, rolling config, and health checks — just not horizontal scale.
> For true multi-replica HA you'd move the backend to PostgreSQL (see below).

**Steps:**

1. Build the image and push it to a registry your cluster can pull from:
   ```
   docker build -f server/Dockerfile -t YOUR_REGISTRY/nds-api:1.0 .   # from repo root
   docker push YOUR_REGISTRY/nds-api:1.0
   ```
   (Remember to put your app file in as `index.html` before building.)

2. Edit `k8s/nds-api.yaml` and replace `YOUR_REGISTRY/nds-api:1.0` with that
   image. If your cluster needs a specific `storageClassName`, set it in the
   PersistentVolumeClaim.

3. Apply:
   ```
   kubectl apply -f k8s/nds-api.yaml
   ```
   This creates a `nds` namespace, a 1Gi PersistentVolumeClaim (`nds-data`),
   the Deployment, and a ClusterIP Service.

4. **Reach it.** For a quick test:
   ```
   kubectl -n nds port-forward svc/nds-api 8000:80
   ```
   then open `http://localhost:8000`. For your team, expose it properly with the
   optional Ingress:
   ```
   # edit the hostname/TLS first, then:
   kubectl apply -f k8s/ingress.yaml
   ```

**Health checks:** liveness and readiness probes hit `/api/v1/ping`, so
Kubernetes restarts the pod if it stops responding and only sends traffic once
it's ready.

**Your data** lives on the `nds-data` PersistentVolumeClaim, mounted at `/data`
inside the pod (`NDS_DB_PATH=/data/nds.db`). It survives pod restarts, image
updates and rescheduling. Back it up by snapshotting the PVC (or copy the file
out: `kubectl -n nds cp <pod>:/data/nds.db ./nds-backup.db`). The app's
**Settings → Export JSON** is a good portable second backup.

**Updating the app:** build and push a new image tag, change the `image:` line,
and `kubectl apply` again — Kubernetes rolls the new pod in and the volume (your
data) is untouched.

**Scaling to PostgreSQL (only if you need multi-replica HA):** run Postgres in
the cluster (or use a managed instance), adjust `server.py` to use it instead of
SQLite, drop the single-replica/`Recreate` constraints, and remove the PVC. This
is a deliberate, larger change — don't take it on unless availability genuinely
requires it.

---

## Running properly without Docker (for IT)

For day-to-day use you'll want it to stay running and ideally use HTTPS:

- **Keep it running:** install it as a service with NSSM (Windows) or a
  `systemd` unit (Linux) so it starts on boot and restarts if it stops.
- **HTTPS + friendly name:** put it behind a reverse proxy (IIS with ARR,
  nginx, or Caddy) that terminates TLS and forwards to `127.0.0.1:8000`.
  (This applies equally to the Docker setup — proxy to the published port.)
- **Restrict access:** limit it to your internal network / VPN, or add
  authentication at the proxy. The app's own admin lock guards destructive
  actions, but network-level access control is the stronger boundary.
- **Bigger teams:** SQLite is fine for a workgroup. If you outgrow it, the same
  `server.py` can be pointed at PostgreSQL or SQL Server with small changes.

---

## How it protects against two people clashing

Every record carries a version number. When the app saves, it sends the version
it last saw. If someone else saved first, the version won't match and the server
replies **409 (Conflict)**; the app then reloads the current data and asks the
person to re-apply their edit. The change log and the config/taxonomy are
treated as append-only / last-write-wins, so they never block you.
