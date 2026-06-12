variable "proxmox_endpoint" {
  description = "Proxmox API URL"
  type        = string
}

variable "proxmox_api_token" {
  description = "Proxmox API token in form user@realm!tokenid=secret"
  type        = string
  sensitive   = true
}

variable "target_node" {
  description = "Proxmox node to create VMs on"
  type        = string
  default     = "svrhost"
}

variable "template_id" {
  description = "VM ID of the cloud-init template to clone"
  type        = number
  default     = 9000
}

variable "vm_datastore" {
  description = "Proxmox storage for VM disks"
  type        = string
  default     = "local-lvm"
}

variable "network_bridge" {
  description = "Linux bridge VMs attach to"
  type        = string
  default     = "vmbr1"
}

variable "vm_gateway" {
  description = "Default gateway for VMs"
  type        = string
  default     = "10.10.10.1"
}

variable "vm_dns" {
  description = "DNS resolver for VMs (AD DNS server)"
  type        = string
  default     = "10.10.15.20"
}

variable "ssh_public_key" {
  description = "SSH public key injected into VMs via cloud-init"
  type        = string
}

variable "vm_username" {
  description = "Default user created by cloud-init"
  type        = string
  default     = "firdaus"
}