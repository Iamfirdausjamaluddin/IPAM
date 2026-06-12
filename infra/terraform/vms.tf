variable "vms" {
  description = "All project VMs, keyed by name"
  type = map(object({
    vm_id  = number
    ip     = string
    cores  = number
    memory = number
    disk   = number
  }))
  default = {
    "k3s-server" = {
      vm_id  = 700
      ip     = "10.10.14.100/24"
      cores  = 2
      memory = 2048
      disk   = 20
    }
    "k3s-agent-1" = {
      vm_id  = 701
      ip     = "10.10.14.101/24"
      cores  = 2
      memory = 2048
      disk   = 20
    }
    "k3s-agent-2" = {
      vm_id  = 702
      ip     = "10.10.14.102/24"
      cores  = 2
      memory = 2048
      disk   = 20
    }
    "vault" = {
      vm_id  = 703
      ip     = "10.10.14.103/24"
      cores  = 1
      memory = 1024
      disk   = 20
    }
  }
}

resource "proxmox_virtual_environment_vm" "vm" {
  for_each = var.vms

  name      = each.key
  node_name = var.target_node
  vm_id     = each.value.vm_id
  pool_id   = "ipam-tf"

  clone {
    vm_id = var.template_id
    full  = true
  }

  agent {
    enabled = false
  }

  cpu {
    cores = each.value.cores
    type  = "host"
  }

  memory {
    dedicated = each.value.memory
  }

  disk {
    datastore_id = var.vm_datastore
    interface    = "scsi0"
    size         = each.value.disk
  }

  network_device {
    bridge = var.network_bridge
  }

  initialization {
    ip_config {
      ipv4 {
        address = each.value.ip
        gateway = var.vm_gateway
      }
    }

    dns {
      servers = [var.vm_dns]
    }

    user_account {
      username = var.vm_username
      keys     = [trimspace(var.ssh_public_key)]
    }
  }
}