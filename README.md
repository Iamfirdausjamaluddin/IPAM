# Homelab IPAM

A self-hosted IP Address Management dashboard for my homelab — built end-to-end to learn modern DevOps practices.

> **Status:** 🚧 Under active development — currently in Phase 0 (project foundation).

---

## What is this?

A web app that shows which IPs in my homelab subnet (`10.10.0.0/20`) are in use, free, or reserved — so I can safely pick an IP before creating a new VM in Proxmox.

### The problem it solves

In my setup, pfSense DHCP hands out IPs to VMs, then I convert each VM to a static IP inside its OS. Once converted, pfSense no longer tracks that IP as "taken" — creating a real risk of IP conflicts. This IPAM is the source of truth for those static assignments.

### What it does

- Pings every IP in the assignment range every few minutes
- Lets me record reservations (which IP belongs to which VM)
- Flags **rogue** devices (responding to ping but not reserved)
- Flags **conflicts** (multiple data sources disagreeing)
- Will eventually expose Prometheus metrics and send alerts

---

## Why this project exists

I'm an IT infrastructure professional learning programming and DevOps. Rather than build a throwaway tutorial app, I'm building something I actually use, while exercising every modern DevOps tool end-to-end:

| Layer | Tool |
|---|---|
| Backend | Python 3.12 + FastAPI |
| Frontend | React + Vite + Tailwind CSS |
| Database | PostgreSQL 16 + Alembic migrations |
| Containerization | Docker |
| Orchestration | K3s (lightweight Kubernetes) |
| Provisioning | Terraform (`bpg/proxmox` provider) |
| Configuration | Ansible |
| Secrets | HashiCorp Vault + External Secrets Operator |
| CI/CD | GitHub Actions |
| Monitoring | Prometheus + Grafana + Alertmanager |
| Logging | Loki |
| Ingress / TLS | Nginx Ingress Controller + cert-manager |

---

## Project status by phase

- [x] **Phase 0** — Project foundation (repo, structure, README, .gitignore)
- [ ] **Phase 1** — FastAPI backend skeleton
- [ ] **Phase 2** — PostgreSQL + Alembic migrations
- [ ] **Phase 3** — Background IP scanner
- [ ] **Phase 4** — React frontend with subnet tabs
- [ ] **Phase 5** — Containerization (Docker + docker-compose)
- [ ] **Phase 6** — Terraform: provision K3s + Vault VMs on Proxmox
- [ ] **Phase 7** — Ansible: install K3s and Vault
- [ ] **Phase 8** — Deploy to Kubernetes with Ingress + HTTPS
- [ ] **Phase 9** — Vault for secrets management
- [ ] **Phase 10** — Prometheus, Grafana, Loki, Alertmanager
- [ ] **Phase 11** — GitHub Actions CI/CD
- [ ] **Phase 12** — HPA, resource limits, backups, rollback

Phase completion summaries live in [`docs/`](./docs).

---

## Repository layout

---

## Local development

> Instructions will be added as each phase completes. Currently nothing to run — Phase 1 will produce the first runnable artifact.

---

## Safety commitments

This project is a **passive observer** of the network. It will never:

- Modify any pfSense firewall rule, DHCP setting, DNS setting, or interface
- SSH into pfSense to change configuration
- Touch existing production VMs (Active Directory, PKI CAs, BeyondTrust, etc.)

The IPAM only sends ICMP ping packets (the same ones any laptop sends with `ping`) and stores reservations in its own database.

---

## License

MIT — see [LICENSE](./LICENSE).