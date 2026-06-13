# Phase 7 Complete — Configuration Management (Ansible)

Branch: `phase-7-config-mgmt`. Ansible now owns the *in-VM* layer of the
stack. The four bare VMs that Phase 6 (Terraform) created are configured into
a working three-node K3s cluster plus a standalone Vault host — entirely
through playbooks run from WSL2 Ubuntu over SSH, using the same `firdaus` key
and static IPs, no guest agent needed. The Terraform/Ansible boundary stayed
clean: Terraform = VM existence, Ansible = what runs inside them.

## What Phase 7 delivered
- A **3-node K3s cluster** (1 control plane + 2 workers), all `Ready`.
- **Vault installed** on its own VM via HashiCorp's apt repo, service present,
  left **sealed/uninitialized** by design (initialization is Phase 9).
- A reusable Ansible project under `infra/ansible/` parallel to
  `infra/terraform/`, with a grouped inventory and three playbooks.

## The cluster (live, verified)
| Node        | IP            | K8s role       | K3s version   | Status |
|-------------|---------------|----------------|---------------|--------|
| k3s-server  | 10.10.14.100  | control-plane  | v1.35.5+k3s1  | Ready  |
| k3s-agent-1 | 10.10.14.101  | worker (<none>)| v1.35.5+k3s1  | Ready  |
| k3s-agent-2 | 10.10.14.102  | worker (<none>)| v1.35.5+k3s1  | Ready  |
| vault-1     | 10.10.14.103  | (Vault host)   | Vault v2.0.2  | sealed |

(`ROLES <none>` on the agents is normal — plain workers carry no role label.)

## Project structure
```
infra/ansible/
  inventory/
    hosts.ini                 # grouped inventory: k3s_server, k3s_agents, vault
  playbooks/
    install-k3s-server.yml    # 7.3 control plane
    install-k3s-agents.yml    # 7.4 workers join
    install-vault.yml         # Vault install (sealed)
```
Kept deliberately lean — no `roles/`, `group_vars/` yet. Folders get added when
a task actually needs them, same minimalism as Phase 6.

## Sub-steps
- **7.1 — SSH identity into WSL (the cross-boundary plumbing).** Terraform's
  key was generated/stored on the **Windows** side; Ansible runs in **WSL2**,
  which has its own `~/.ssh`. Copied `id_ed25519` from
  `/mnt/c/.../.ssh/` into WSL's `~/.ssh/` and `chmod 600` it. Chose **copy into
  WSL** over **point-at-the-Windows-key-in-place**: files on `/mnt/c` carry
  Windows permissions, and `chmod 600` won't reliably stick there, so SSH
  rejects the key with "UNPROTECTED PRIVATE KEY FILE." Copying off the mount is
  what lets Linux permissions hold. Proved with a manual `ssh` into .100, then
  pre-trusted the other three host keys with `ssh-keyscan -t ed25519 ... >>
  ~/.ssh/known_hosts` to avoid interactive fingerprint prompts.
- **7.2 — Inventory + connectivity.** INI inventory grouping hosts by *role*
  (`k3s_server`, `k3s_agents`, `vault`) with shared connection vars in
  `[all:vars]` (`ansible_user`, key path, `ansible_python_interpreter`).
  Validated end-to-end with `ansible all -m ping` → four `pong`s. Hit and fixed
  the "group and host with same name: vault" warning by renaming the host
  `vault` → `vault-1` (group stays `vault`).
- **7.3 — K3s server.** Playbook: `get_url` the official installer →
  `command` to run it with `INSTALL_K3S_EXEC="--write-kubeconfig-mode 644"`
  (readable kubeconfig for Phase 8) → poll `kubectl get nodes` until `Ready`.
  Idempotent via `creates: /etc/systemd/system/k3s.service`.
- **7.4 — K3s agents (the real Ansible pattern).** Two-play playbook:
  Play 1 reads `/var/lib/rancher/k3s/server/node-token` on the server and
  `register`s it; Play 2 installs in agent mode on both workers, pulling the
  token across hosts with
  `{{ hostvars['k3s-server']['k3s_token'].stdout }}` and pointing at
  `K3S_URL=https://10.10.14.100:6443`. Idempotent via
  `creates: /etc/systemd/system/k3s-agent.service`.
- **7.5 — Vault install.** Modern signed-apt-repo recipe: fetch HashiCorp's
  GPG key to `/usr/share/keyrings/`, add the repo with
  `signed-by=...` (NOT deprecated `apt-key`), `apt install vault`. Chose the
  **apt repo over the raw binary** because Vault's *concepts* (sealing,
  policies) are Phase 9's lesson, not hand-writing a systemd unit; the package
  provides the `vault` user, service, and config skeleton for free, matching
  every official Phase 9 guide. Left **uninitialized/sealed** on purpose.

## Key things learned / confirmed this phase
- **The Windows↔WSL SSH boundary is the first real gotcha.** Ansible lives in
  WSL with its own home; Windows keys aren't visible to it automatically, and
  `/mnt/c` can't hold strict Linux permissions. Copy the key in once and every
  later phase (incl. Phase 8 `kubectl`) just works.
- **Cross-host value passing is the core multi-node Ansible skill.**
  `register` a value on one host, read it on another via `hostvars`. This is
  how the join token flowed server → agents, and the pattern reused anywhere
  one machine needs something another produced.
- **Inventory groups encode topology.** Server vs agents being separate groups
  is what lets one playbook treat them differently (server-install vs
  agent-join).
- **Name-agnostic readiness checks beat hardcoded node names.** The "wait for
  Ready" task greps for `Ready` in `kubectl get nodes` rather than a specific
  hostname, so it doesn't depend on what cloud-init named the host. (Here
  cloud-init happened to name them matching the inventory, but not relying on
  that is the safer habit.)
- **Idempotency via `creates:`.** Server and agent installs guard on different
  service files (`k3s.service` vs `k3s-agent.service`), so re-running the
  playbooks is safe.

## ⚠️ Carried-forward item for Phase 9 (Vault) — don't lose this
- **Vault 2.0.x ≠ a rewrite — it's the 1.21 line renamed** under HashiCorp's
  move to IBM's versioning/lifecycle. Architecture is the same as 1.21.
- **`disable_mlock = true` will be REQUIRED in the Vault config in Phase 9.**
  Vault 2.0.2 removed the `cap_ipc_lock` capability at build time, so Vault can
  no longer `mlock()` its memory and won't start cleanly without
  `disable_mlock = true` set. (Trade-off: secrets could be swapped to disk —
  the upstream guidance is to also disable swap on the host. Decide in Phase 9.)

## Verified (live)
- `ansible all -m ping` → 4× `pong`.
- `k3s kubectl get nodes -o wide` on the server → 3 nodes, all `Ready`, correct
  IPs/roles, matching K3s versions.
- Agent `AGE` (~75s) vs server (`3h59m`) confirmed the agents joined fresh into
  the pre-existing control plane (no rebuild).
- `vault version` on .103 → `Vault v2.0.2` (binary installed, on PATH).
- Playbooks are idempotent (guarded installs; status checks are
  `changed_when: false`).

## Operating the stack (quick reference)
- All Ansible runs in **`wsl -d Ubuntu`**, from `infra/ansible/`. Tailscale ON.
- Connectivity test: `ansible all -i inventory/hosts.ini -m ping`
- Re-run a playbook (safe, idempotent):
  `ansible-playbook -i inventory/hosts.ini playbooks/<name>.yml`
- One-off command on a group:
  `ansible <group> -i inventory/hosts.ini -b -m command -a "<cmd>"`
- Inventory is the single place to add/re-IP a node (next free VM ID 704–799,
  free IP from the IPAM).
- Git/Terraform still run in **VS Code PowerShell**; never touch pfSense.

## Next: Phase 8 — Deploy to Kubernetes
Deploy the IPAM app (backend + frontend + Postgres) onto the K3s cluster with
an Ingress and HTTPS. First task is fetching the cluster's kubeconfig from the
server (the `644` mode set in 7.3 makes this clean) and wiring `kubectl` in WSL
to talk to 10.10.14.100. Reminder: never touch pfSense (firewall/DHCP/DNS/NAT/
routing) — non-negotiable.
