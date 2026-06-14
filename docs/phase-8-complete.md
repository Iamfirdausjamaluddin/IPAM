# Phase 8 Complete — Deploy to Kubernetes

Branch context: Phase 8 deployed the IPAM app (backend + frontend) onto the
Phase 7 K3s cluster, fronted by an Nginx Ingress with real, browser-trusted
HTTPS. The database was deliberately placed **outside** the cluster on its own
Terraform-provisioned, Ansible-hardened VM — the production-honest
stateless-cluster / stateful-DB split. Everything is reachable at
`https://ipam.lab.axtarbyte.com` over Tailscale, with a Let's Encrypt cert that
cert-manager auto-renews.

## Architectural decisions (the "why")
- **External-VM Postgres, not in-cluster.** Chosen explicitly to learn how big
  orgs separate concerns: Kubernetes runs the stateless tier (backend/frontend
  pods), the database lives on a dedicated VM the apps connect *out* to. Avoids
  fighting Kubernetes' disposable-pod model with a stateful workload. The
  alternative (in-cluster Postgres operator + Longhorn) was noted as a bigger,
  separate topic, deferred.
- **Private GHCR images + imagePullSecret**, not public. More production-real;
  taught the `imagePullSecret` mechanism. Images: `ghcr.io/iamfirdausjamaluddin/
  ipam-backend:phase8` and `…/ipam-frontend:phase8`.
- **Nginx Ingress, not K3s's bundled Traefik.** Matches the locked stack and is
  the most widely deployed controller (most transferable knowledge). Traefik was
  disabled in-code via Ansible. (Noted: Gateway API is the thing to learn *next*
  after Ingress fundamentals; ingress-nginx is winding down upstream.)
- **HTTPS via Let's Encrypt DNS-01 (Cloudflare), not internal CA.** Deliberate
  choice to learn the real ACME flow rather than repeat the internal-PKI work the
  user already does daily. DNS-01 (not HTTP-01) because there is no public
  inbound path and pfSense is never touched — DNS-01 only writes a public TXT
  record, exposing nothing.
- **Dedicated subdomain `ipam.lab.axtarbyte.com`.** Sidesteps the AD/public
  split-brain on the root domain; gives cert-manager a narrow, scoped slice.
- **Routing Option A:** Ingress sends all traffic to the frontend; the
  frontend's existing nginx reverse-proxies `/api/` → backend (reusing the
  tested Phase 5 proxy with its load-bearing trailing-slash `/api` strip).
- **Seed via a Kubernetes Job**, not a laptop script or startup auto-seed —
  the production-native "run a task once against the cluster" pattern.

## What got built / deployed
- **`ipam-db` VM (VM 704, 10.10.14.110)** — added to Terraform's `vms` map
  (one entry; `for_each` meant zero changes to the four existing VMs; disk 30 GB
  vs 20 for the stateless nodes since a DB accumulates state). qemu-guest-agent
  deliberately omitted (`agent.enabled=false`), consistent with prior phases.
- **Postgres 16 on `ipam-db`** via a new Ansible playbook
  (`infra/ansible/playbooks/install-postgres.yml`): PGDG signed-apt-repo install,
  `ipam` database + least-privilege `ipam` user (NOT superuser), network
  hardening (`listen_addresses='localhost,10.10.14.110'` + `pg_hba.conf` scoped
  to `10.10.14.0/24` with `scram-sha-256`). Added to Ansible inventory as group
  `database` / host `ipam-db`.
- **Kubernetes manifests** under `k8s/`:
  - `namespace.yaml` — `ipam` namespace
  - `backend.yaml` — Deployment (replicas:1, NET_RAW for the scanner's raw
    sockets, `envFrom` the DB secret, `imagePullSecrets`) + ClusterIP Service
  - `frontend.yaml` — Deployment + ClusterIP Service (nginx on :80)
  - `ingress.yaml` — host rule → frontend, cert-manager annotation, TLS block
  - `cluster-issuer-staging.yaml` / `cluster-issuer-prod.yaml`
  - `seed-job.yaml` — one-shot Job running `python seed.py`
- **Cluster add-ons (Helm):** Nginx Ingress Controller (`ingress-nginx` ns,
  got a LoadBalancer IP on the node addresses via K3s ServiceLB), cert-manager
  (`cert-manager` ns, v1.20.2, CRDs enabled).
- **Secrets created:** `ghcr-pull-secret` (docker-registry, ipam ns),
  `ipam-backend-secrets` (DATABASE_URL, ipam ns), `cloudflare-api-token`
  (cert-manager ns).

## Verified working (live)
- Both app pods `1/1 Running`; backend migrated the DB on boot (Alembic), serves
  the API, scanner running.
- App loads at `https://ipam.lab.axtarbyte.com` with a real padlock (no warning),
  cert issued by Let's Encrypt **production**.
- Full request chain confirmed via browser Network tab: `/api/grid/11..15` all
  `200`, ~9.8 kB each (real data).
- Seed Job: `1269 inserted, 0 skipped` — every IP in `10.10.11.10–10.10.15.254`.
- Scanner, after seeding + restart: `probing 1269 IPs`, TCP-fallback rolling
  sweep firing (`100 IP slice … cursor 100/1269`), `10 alive of 1269`,
  `1269 rows updated`. ICMP/TCP from inside the pod reaches the homelab subnet.

## Hard-won gotchas (don't lose these)
- **psycopg3 prefix.** The image uses `psycopg[binary]` (psycopg **3**), so
  `DATABASE_URL` MUST be `postgresql+psycopg://…`, not plain `postgresql://`
  (psycopg2). Wrong prefix = crash on engine creation. Caught from the compose
  file before applying.
- **Postgres 15+ `public` schema lockdown.** PG15 removed the default CREATE
  grant on `public`. The `ipam` user (even as DB owner) couldn't create tables →
  Alembic failed with `permission denied for schema public`. Fix: Ansible task
  making `ipam` the **owner** of the `public` schema in the `ipam` DB.
- **Ansible `become_user` needs `acl` on the target.** Switching root→postgres
  for DB tasks failed (`chmod: invalid mode 'A+user:...'`) until `acl` was
  installed on `ipam-db`. Added to the prerequisites task.
- **K3s disable-Traefik via config drop-in, not systemd edit.** Wrote
  `/etc/rancher/k3s/config.yaml.d/disable-traefik.yaml` (`disable: [traefik]`)
  + K3s restart, via Ansible. K3s actively uninstalls the addon and won't
  recreate it. Avoids the fragile systemd-ExecStart edit.
- **Split-brain DNS broke cert-manager's DNS-01 self-check.** cert-manager
  wrote the `_acme-challenge` TXT to Cloudflare fine (`Presented: true`), but its
  propagation self-check used the cluster's resolver (AD DNS 10.10.15.20, which
  is authoritative for the internal zone and never sees the public TXT) → stuck
  `pending` forever. Fix: `helm upgrade` cert-manager with
  `--dns01-recursive-nameservers-only` +
  `--dns01-recursive-nameservers=1.1.1.1:53,8.8.8.8:53`. Cert issued within
  minutes after.
- **Always validate ACME on Let's Encrypt staging first**, then swap to prod —
  staging has generous rate limits; prod will lock you out after a few failures.
- **Seed-then-restart ordering.** The long-running backend pod had cached an
  empty `ip_addresses` view; seeding via the Job didn't make the *running*
  scanner see the rows. `kubectl rollout restart deployment/ipam-backend` gave a
  fresh DB view and the scanner picked up all 1269. Lesson: seed/migration runs
  before (or triggers a restart of) the consuming app.
- **kubectl/Helm live in WSL only** (kubeconfig is in WSL `~/.kube/config`,
  server line rewritten 127.0.0.1→10.10.14.100). Running kubectl in PowerShell
  hits localhost:8080 and fails. Docker (build/tag/push) stays on PowerShell.
- **Run kubectl from the repo root**, reference paths as `k8s/...` — running
  inside `k8s/` and re-typing the prefix causes the `k8s/k8s/...` "path does not
  exist" trap (hit several times).

## Stopgaps to clean up in Phase 9 (Vault + ESO)
These are deliberate, temporary, and the exact things Vault/External Secrets
Operator should replace:
- **Postgres `ipam` password** lives in gitignored `infra/ansible/secrets.yml`
  (plaintext). The gitignore guard was verified with `git check-ignore` BEFORE
  the file was created.
- **`DATABASE_URL`** sits in a plain K8s Secret (`ipam-backend-secrets`).
- **Cloudflare API token** sits in a plain K8s Secret (`cloudflare-api-token`,
  scoped to `Zone:DNS:Edit` on `axtarbyte.com` only — least privilege).
- **GHCR pull token** is a 90-day classic PAT (`read:packages` only). Set a
  renewal reminder; long-term this shouldn't be a hand-managed PAT.
- (Earlier in the session a write-scoped PAT was accidentally echoed to the
  terminal and **revoked immediately**, replaced with a fresh one. Habit
  reinforced: exposed credential → revoke, no exceptions.)

## Operating notes / quick reference
- App URL: `https://ipam.lab.axtarbyte.com` (Tailscale ON). Laptop resolves it
  via a **hosts-file** entry → 10.10.14.100 (the ingress node IP). A proper AD
  DNS A record is the cleaner long-term option (AD DNS is allowed; pfSense is
  not). Public Cloudflare DNS holds only the transient ACME TXT — never an A
  record pointing at private IPs.
- Pods: `kubectl get pods -n ipam`. Logs: `kubectl logs -n ipam
  deployment/ipam-backend`. Re-seed (idempotent): re-apply `k8s/seed-job.yaml`
  (delete the old completed Job first if the name collides).
- Ingress front door is the `ingress-nginx-controller` LoadBalancer Service on
  node IPs 10.10.14.100–102, ports 80/443 (the slot Traefik vacated).
- Never touch pfSense (firewall/DHCP/DNS/NAT/routing) — non-negotiable.

## Next: Phase 9 — Secrets with Vault
**Start by cutting a `phase-9-vault` branch** (`git checkout -b phase-9-vault`) —
Phase 8 was committed straight to `main`, so this returns to the branch-per-phase
rhythm.

Then: initialize/unseal the Phase 7 Vault (still sealed by design), wire the
**`disable_mlock = true`** requirement flagged in the Phase 7 doc (Vault 2.0.x
removed `cap_ipc_lock`), and migrate the stopgap secrets above into Vault, synced
into the cluster via External Secrets Operator. Reminder: never touch pfSense.