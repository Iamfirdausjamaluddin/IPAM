# Phase 6 Complete — Infrastructure as Code (Terraform)

Branch: `phase-6-iac`. Terraform now owns the project's VM layer. Four VMs —
the K3s server, two K3s agents, and a standalone Vault VM — are created and
managed as code on Proxmox via the `bpg/proxmox` provider, under a tightly
scoped API token that cannot touch pfSense or any production VM.

## What Phase 6 delivered
The cluster's infrastructure went from "click VMs together by hand in the
Proxmox UI" to a single `terraform apply` that stamps out all four VMs from
one parameterized resource block. These are the VMs Phase 7 (Ansible) will
install K3s and Vault onto. This phase built the machines, not what runs on
them — the Terraform/Ansible boundary is deliberately clean (Terraform =
infrastructure existence; Ansible = in-VM configuration).

### The VMs
| Name        | VM ID | IP             | Role                         | CPU/RAM   |
|-------------|-------|----------------|------------------------------|-----------|
| k3s-server  | 700   | 10.10.14.100   | K3s control plane            | 2c / 2 GB |
| k3s-agent-1 | 701   | 10.10.14.101   | K3s worker                   | 2c / 2 GB |
| k3s-agent-2 | 702   | 10.10.14.102   | K3s worker                   | 2c / 2 GB |
| vault       | 703   | 10.10.14.103   | Vault (outside the cluster)  | 1c / 1 GB |

All four cloned from template 9000, static IPs via cloud-init, DNS at the AD
server 10.10.15.20, SSH key injected, placed in the `ipam-tf` pool.

## Sub-steps
- **6.1 — Scoped Proxmox credential (safety foundation).** Built the auth layer
  *before* any Terraform. Created a custom role `TerraformIPAM` with a minimal
  privilege set, a dedicated `terraform-ipam@pve` user (no shell login), a
  resource pool `ipam-tf`, and an API token. Crucially, the role is bound by
  ACL to narrow paths — `/pool/ipam-tf`, `/storage/local-lvm`,
  `/nodes/svrhost`, `/sdn/zones`, and `/vms/9000` (template clone access) —
  NOT to `/` as most guides do. Result: even a runaway Terraform run cannot
  touch pfSense, because pfSense is outside the pool and the token has no
  VM.Config / VM.PowerMgmt rights over it. The pfSense non-negotiable is now
  enforced at the permission layer, not just by discipline.
- **6.2 — Terraform project skeleton.** Provider config in `infra/terraform/`
  (`versions.tf` pinning `bpg/proxmox ~> 0.66`, `providers.tf`, `variables.tf`,
  gitignored `terraform.tfvars` with endpoint + token). `insecure = true` for
  Proxmox's self-signed cert. Token-only auth, no SSH block. `terraform init`
  then `plan` proved auth end to end (laptop -> Tailscale -> 192.168.5.50:8006
  -> scoped token) with a clean "No changes."
- **6.3 — One test VM, then scale.** Built VM 700 alone first to calibrate the
  role against reality (the apply -> 403 -> grant-named-privilege loop tightened
  the role to exactly what's needed), then refactored to `for_each` and created
  the remaining three in one apply.

## Privilege calibration (how the role was tightened)
Creating VM 700 surfaced two ACL gaps the API returned as HTTP 403, each
naming exactly the missing piece:
- `(/vms/9000, VM.Clone)` — the token had no rights on the template (it's
  outside the pool). Fixed with a single narrow grant: `pveum aclmod /vms/9000`.
  Scoped to the ONE template, not all VMs — pfSense stays untouchable.
- `(/sdn/zones/localnetwork/vmbr1, SDN.Use)` — newer Proxmox gates ALL bridge
  attachment (even plain Linux bridges) behind `SDN.Use`. Had to restore the
  privilege + grant `/sdn/zones`. `SDN.Use` is a *use* (attach-to-bridge)
  permission — it does NOT allow creating/modifying/deleting bridges or network
  config, so it stays clean against the pfSense rule.

## The for_each refactor (the real pattern)
The four VMs are defined as a `map(object(...))` variable (`vms`) and rendered
by a single `proxmox_virtual_environment_vm.vm` resource using `for_each`, with
`each.key` as the name/hostname and `each.value.*` for per-VM id/ip/cpu/ram/disk.
One block, four VMs; adding a fifth is one map entry, not a new resource block.
The pre-existing VM 700 was migrated into the new addressing with
`terraform state mv 'proxmox_virtual_environment_vm.k3s_server'
'proxmox_virtual_environment_vm.vm[\"k3s-server\"]'` so the refactor recognized
the running VM instead of destroy-and-recreating it. Verified with a plan
showing `3 to add, 0 to change, 0 to destroy` BEFORE applying — the gate that
protected 700.

## The qemu-guest-agent decision (and why it's deferred)
The cloud-init template (9000) does NOT have `qemu-guest-agent` installed, and
the package state inside it is stale (months-old held-back kernel headers / vim
deps). This caused a cascade when explored:
- With `agent { enabled = true }`, Terraform waits up to 15 min for an agent
  that never answers, then times out (the VM itself is fine — only the handshake
  hangs).
- Attempting to fix the template via a throwaway clone (9001) hit, in sequence:
  cloud-init ISO on wrong storage (`local` vs `local-lvm`), forgotten template
  credentials, no DHCP lease, a full 2 GB root disk, and an unresolvable apt
  dependency knot from the stale package state. Every problem was an artifact of
  *manually booting* a template only ever designed to be Terraform-cloned.

**Decision:** set `agent { enabled = false }` on all VMs and move on. Rationale:
the agent only provides (a) Proxmox UI IP display and (b) graceful guest
shutdown — neither needed here, because IPs are assigned statically (already
known) and the VMs are rebuildable cattle. Nothing in Phases 7–10 depends on
it: Ansible and K3s reach the nodes over SSH by static IP. The PROPER fix — a
Packer-built golden image with the agent (and clean package state) baked in —
is deferred to **Phase 11 (CI/CD)**, which is where template-building belongs
as a pipeline artifact. Solving it now would mean doing Phase 11's work out of
order before the CI scaffolding exists.

Rejected alternatives and why:
- *Terraform cloud-init snippet (`packages: [qemu-guest-agent]`)* — requires the
  "Snippets" datastore content-type AND an SSH connection from the provider to
  the Proxmox host (snippet upload goes over SFTP, not the API). Adding host SSH
  to the provider expands the credential well beyond the least-privilege token
  boundary built in 6.1 — bad trade for a convenience feature.
- *virt-customize on the host* — cleanest end state but most upfront work and
  involves libguestfs mounting disk images on the production hypervisor.

## Verified (live)
- `terraform apply` → `Apply complete! Resources: 3 added, 0 changed,
  0 destroyed` (700 untouched by the for_each migration).
- SSH into all four VMs by static IP (10.10.14.100–103) as user `firdaus` with
  the injected key — proves each booted, cloud-init set the static IP, and the
  key landed.
- `pvesh get /pools/ipam-tf` lists all four VMs (700–703) — confirms they're
  inside the scoped safety boundary.
- The four IPs reserved in the IPAM dashboard (10.10.14.100–103) → read BLUE
  (reserved + alive). Closes the observe-vs-intend loop: the project's own tool
  now records the static assignments that pfSense DHCP is blind to — exactly the
  green-trap problem the IPAM exists to solve, applied to infra the IPAM helped
  provision safely.

## Key things learned / confirmed this phase
- **Scope the credential, not just the behavior.** Binding the role to a pool +
  specific paths (not `/`) makes the pfSense safety rule a property of the
  permission system. The 403s during 700's creation were the role being
  *calibrated to reality* — each named the exact missing privilege.
- **`SDN.Use` gates plain bridges too** on current Proxmox — the mental model
  ("plain bridge, no SDN") didn't match the permission check; the error told the
  truth.
- **Manual boot of a Terraform-only template is a trap.** Templates designed to
  be cloned-and-configured by Terraform carry assumptions (cloud-init storage,
  no known credentials, DHCP, stale apt) that only bite when you boot them by
  hand. Don't.
- **`for_each` + `terraform state mv`** is the clean way to go from one
  hand-written resource to a parameterized fleet without rebuilding what exists.
- **PowerShell quoting for state mv:** the resource index needs escaped inner
  quotes — `'...vm[\"k3s-server\"]'` — or PowerShell strips them and Terraform
  errors with "Index value required."
- **Agent is optional infrastructure.** Knowing what a convenience feature
  actually buys you (and that nothing downstream needs it) is what makes
  deferring it the right call rather than a cop-out.

## Operating the stack (quick reference)
- Plan: `terraform plan` (run in VS Code PowerShell terminal)
- Apply: `terraform apply` (review plan, type `yes`)
- The `vms` map in `vms.tf` is the single place to add/resize/re-IP VMs
- Add a VM: new entry in the `vms` map (next free ID 704–799, free IP from IPAM)
- Token/endpoint live in `terraform.tfvars` (gitignored — never committed)
- Reach VMs: `ssh firdaus@10.10.14.<host>` (Tailscale ON)

## Carried-forward items (not blocking)
1. qemu-guest-agent + clean golden image → Phase 11 (Packer in CI/CD).
2. `agent { enabled = false }` is a global default via the resource block; if a
   future VM needs the agent, install it manually then flip the flag for that VM.
3. Template 9000 retained as-is (untouched, known-good for cloning); its stale
   internal package state is irrelevant to clones since Terraform configures
   them fresh, but it's the thing Phase 11 replaces.

## Next: Phase 7 — Configuration Management (Ansible)
Ansible (run via `wsl -d Ubuntu` per environment rules) installs K3s on the
server + two agents (forming the cluster) and Vault on 703. Inventory targets
the four static IPs (10.10.14.100–103) over SSH with the `firdaus` key — no
guest agent needed. Reminder: never touch pfSense (firewall/DHCP/DNS/NAT/
routing) — non-negotiable.
