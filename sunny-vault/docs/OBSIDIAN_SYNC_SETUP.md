---
id: obsidian-sync-setup
type: infrastructure
status: reference
created: 2026-08-18
tags: [obsidian, sync, setup, documentation]
---

# Obsidian Sync Setup — Real-Time Sync on TrueNAS Scale

**Goal**: Store your Obsidian vault's sync backend on TrueNAS Scale, get near-instant real-time updates on Windows, and full view/edit on iOS — with **no subscriptions** and **no open ports**.

---

## TL;DR — The Recommended Stack

| Piece | What it does | Cost |
|-------|-------------|------|
| **CouchDB** (custom app on TrueNAS Scale) | The sync database every device talks to | Free (open source) |
| **Self-hosted LiveSync** (Obsidian community plugin) | Real-time, change-by-change sync built into Obsidian on Windows and iOS | Free |
| **Tailscale** (app on TrueNAS Scale) | Private mesh VPN for remote access without opening ports, and free HTTPS certs for iOS | Free (personal tier) |

Every device keeps a **local copy** of the vault and syncs through CouchDB. Nothing is exposed to the internet.

### Why This Instead of Syncthing?

Syncthing is great on Windows, but **iOS is the deciding factor**:
- **LiveSync runs inside Obsidian on iOS** — no separate app, and it's genuinely real-time (CouchDB's live change feed) while the app is open
- **Syncthing on iOS** needs a helper app (Möbius Sync — one-time purchase past 20 MB; or SyncTrain — free) and iOS only syncs while the app is **in the foreground**, so edits can lag and cause conflicts

LiveSync is the only option that gives true real-time on **both** Windows and iOS, for free, with no open ports.

**Important caveat**: Obsidian's **iOS** client requires the server to be reached over **HTTPS with a valid certificate**. That's the one fiddly part — and it's exactly why Tailscale is in the stack: it hands you a free, valid HTTPS certificate without opening a single port.

---

## Architecture at a Glance

```
Windows PC ┐
│  Obsidian + LiveSync plugin  ──┐
iPhone/iPad┘                      │  HTTPS over Tailscale
▼                                 │  (no ports opened)
┌───────────────────────────────────┐
│            TrueNAS Scale          │
│  ┌───────────┐    ┌──────────────┐│
│  │ Tailscale │───▶│  CouchDB     ││
│  │  (HTTPS)  │    │ :5984 (vault)││
│  └───────────┘    └──────────────┘│
└───────────────────────────────────┘
```

---

## Prerequisites

- TrueNAS Scale **24.10 "Electric Eel" or newer** (these use Docker for apps)
- A dataset/folder on a pool for CouchDB's data, e.g. `/mnt/<yourpool>/apps/couchdb`
- A free **Tailscale account** (sign in with Google/Microsoft/GitHub)
- Obsidian installed on your Windows PC(s) and on iOS

---

## Part 1 — Install CouchDB on TrueNAS Scale

1. Create two folders under your apps dataset:
   - `/mnt/<yourpool>/apps/couchdb/data`
   - `/mnt/<yourpool>/apps/couchdb/config`

2. In the config folder, create a file named **local.ini** with the following contents. This is what makes CouchDB compatible with LiveSync:

```ini
[couchdb]
single_node = true
max_document_size = 50000000

[chttpd]
require_valid_user = true
max_http_request_size = 4294967296
enable_cors = true
bind_address = 0.0.0.0

[chttpd_auth]
require_valid_user = true

[httpd]
WWW-Authenticate = Basic realm="couchdb"
enable_cors = true

[cors]
credentials = true
origins = app://obsidian.md,capacitor://localhost,http://localhost
headers = accept, authorization, content-type, origin, referer
methods = GET, PUT, POST, HEAD, DELETE
max_age = 3600
```

**Note**: 
- `app://obsidian.md` = Obsidian desktop
- `capacitor://localhost` = Obsidian mobile
If either origin is missing, that platform silently fails to sync.

3. In TrueNAS: **Apps → Discover Apps → ** (three-dot menu, top right) **→ Install via YAML**

Name: `obsidian-couchdb`

YAML content:
```yaml
services:
  couchdb:
    image: couchdb:3
    container_name: obsidian-couchdb
    restart: unless-stopped
    environment:
      COUCHDB_USER: obsidian
      COUCHDB_PASSWORD: <STRONG_PASSWORD>
    ports:
      - "5984:5984"
    volumes:
      - /mnt/<yourpool>/apps/couchdb/data:/opt/couchdb/data
      - /mnt/<yourpool>/apps/couchdb/config/local.ini:/opt/couchdb/etc/local.d/local.ini
```

4. Click **Install** and wait for the app status to show **Running**.

---

## Part 2 — Initialize CouchDB

1. In a browser on your LAN, open `http://<truenas-lan-ip>:5984/_utils` (CouchDB's admin UI, "Fauxton"). Log in with `obsidian / <STRONG_PASSWORD>`.

2. Go to **Setup → Configure a Single Node** and confirm/finish it. This creates the required system databases (_users, _replicator, _global_changes).

3. Quick sanity check — in a shell (or your browser), this should return JSON, not an error:
```bash
curl http://obsidian:<STRONG_PASSWORD>@<truenas-lan-ip>:5984/
```

You do **not** need to manually create the vault database — the LiveSync plugin will create it for you in Part 4.

---

## Part 3 — Tailscale: Private Access + Free HTTPS (iOS-Critical)

Tailscale gives you two things at once: reach your NAS from anywhere **without opening ports**, and a **valid HTTPS certificate** that iOS Obsidian demands.

1. In the [Tailscale admin console](https://login.tailscale.com/admin), generate an **Auth Key** (Settings → Keys).

2. In TrueNAS: **Apps → Discover Apps →** search **Tailscale → Install**. Paste the Auth Key into the AuthKey field, accept defaults, **Install**. When it's Running, your TrueNAS appears in your Tailscale **Machines** list with an address like `100.x.y.z` and a name like `<truenas-host>.<your-tailnet>.ts.net`.

3. Install the **Tailscale app** on each Windows PC and on iOS (App Store), and sign in to the **same** account. All your devices are now on one private network.

4. **Enable HTTPS certificates**: in the Tailscale admin console → **DNS**, enable **MagicDNS** and **HTTPS Certificates**.

5. **Expose CouchDB as HTTPS** using Tailscale Serve. From a TrueNAS shell, exec into the Tailscale container and run:
```bash
tailscale serve --bg --https=443 http://127.0.0.1:5984
```

Tailscale now serves `https://<truenas-host>.<your-tailnet>.ts.net/` with a **real, auto-renewing certificate**, proxying to CouchDB — reachable by your devices anywhere, no ports opened.

**Fallback**: If your TrueNAS Tailscale app doesn't let you run `tailscale serve`, run a tiny reverse proxy instead (Nginx Proxy Manager or Caddy as another custom app) and point it at `http://<truenas-lan-ip>:5984`, using a certificate fetched with:
```bash
tailscale cert <truenas-host>.<your-tailnet>.ts.net
```

Same result: a valid HTTPS endpoint with no open ports.

**Your server URL for the next steps is**: `https://<truenas-host>.<your-tailnet>.ts.net`

---

## Part 4 — Set Up LiveSync on Windows (Your "Source of Truth" Device)

Do the **first-ever** setup on the device that already has your real vault, so nothing gets overwritten.

1. In Obsidian: **Settings → Community plugins →** turn them on → **Browse →** search **"Self-hosted LiveSync" →** Install → Enable.

2. Open **Self-hosted LiveSync** settings → run the **🧙 Setup wizard** (or "Set up a new remote"). Enter:
   - **URI**: `https://<truenas-host>.<your-tailnet>.ts.net`
   - **Username / Password**: `obsidian / <STRONG_PASSWORD>`
   - **Database name**: `obsidiandb` (any name; it's created automatically)
   - **End-to-end passphrase**: pick a strong one (encrypts your notes on the server — remember it, you'll need it on every device)

3. Click **Test Database Connection** and **Check config** — resolve anything flagged. Then **Apply** and let the first full sync complete.

4. Once synced, run **"Copy setup URI"** from the plugin. You'll get an encrypted string — this bundles all the settings above so other devices join in seconds. Keep it handy (and the passphrase).

---

## Part 5 — Set Up iOS

1. Install **Obsidian** from the App Store. Create a **new empty vault** (don't try to import anything yet).

2. Ensure the **Tailscale** app is connected (toggle on).

3. In the new vault: **Settings → Community plugins →** install & enable **Self-hosted LiveSync**.

4. In LiveSync settings choose **"Open setup URI"**, paste the string from Part 4, and enter your **passphrase**. It configures everything and pulls the vault down. Done — you can now view and edit on iOS, and changes flow both ways in real time.

Repeat Part 5's paste-the-URI flow for any additional Windows PC, iPad, Mac, or Android device.

---

## Part 6 — Verify It's Real-Time

Open the vault on Windows and iOS side by side (both with Tailscale on). Type in a note on one; it should appear on the other within a second or two. The LiveSync status icon in the corner shows activity (⏳ syncing / ✅ idle).

---

## Troubleshooting

**Desktop syncs but iOS won't connect / "connection refused"**  
Almost always the HTTPS requirement. Confirm you're using the `https://…ts.net` URL (not `http://…:5984`) on iOS, that Tailscale is toggled on, and that HTTPS certs are enabled in the Tailscale console.

**iOS is rejected with a CORS/401 error**  
Your local.ini is missing `capacitor://localhost` in the `[cors]` origins line, or CORS isn't enabled. Fix local.ini and restart the CouchDB app.

**Large notes/attachments fail to sync**  
`max_http_request_size` / `max_document_size` weren't applied — verify local.ini mounted correctly (check the app's logs in TrueNAS).

**Duplicate/conflicting notes appear**  
Usually a device edited offline for a while. LiveSync flags conflicts for manual merge; syncing all devices once right after setup avoids most of it.

**"Database is not initialized"**  
Redo the Fauxton **Single Node** setup in Part 2.

**Remote (off-home) access fails**  
The device isn't on the tailnet — open the Tailscale app and make sure it's connected and signed into the same account.

---

## Alternative: Syncthing (If You'd Rather Avoid CouchDB)

Simpler concept (plain file sync), but weaker on iOS.

1. Install the **Syncthing** app on TrueNAS Scale (Discover Apps) and the **Syncthing** app on each Windows PC.

2. Point Syncthing at your vault **folder** on each device and share the folder between them (pair via device IDs).

3. For no-port remote access, use the same **Tailscale** setup from Part 3 so devices connect directly.

4. **iOS**: install **SyncTrain** (free) or **Möbius Sync** (free ≤ 20 MB, one-time purchase for unlimited) and add the shared folder.

**Trade-offs**: iOS only syncs while the app is **open/foreground**, so it's not truly real-time there and is more prone to conflicts. Real-time on Windows is fine. Choose this only if you specifically want file-based sync over a database.

---

## References

- [Self-hosted LiveSync — Obsidian plugin](https://community.obsidian.md/plugins/obsidian-livesync)
- [GitHub: vrtmrz/obsidian-livesync](https://github.com/vrtmrz/obsidian-livesync)
- [Self-hosting a Server — LiveSync docs](https://deepwiki.com/vrtmrz/obsidian-livesync/2.2-self-hosting-a-server)
- [TrueNAS Tailscale Integration](https://tailscale.com/docs/integrations/truenas)
