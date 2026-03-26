provider "vsphere" {
  user           = var.vsphere_user
  password       = var.vsphere_password
  vsphere_server = var.vsphere_server
  allow_unverified_ssl = true
}

# 建立高度隔離的 Windows Agent 測試網段 (防嗅探與偽造)
resource "vsphere_distributed_port_group" "isolated_windows_pg" {
  name                            = "VLAN-100-Windows-Isolated"
  vlan_id                         = 100
  allow_promiscuous               = false
  allow_mac_changes               = false
  allow_forged_transmits          = false
}
