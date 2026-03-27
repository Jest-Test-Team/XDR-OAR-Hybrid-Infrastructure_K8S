# 建立 K8s 應用網段，對應架構圖中的 VLAN 20。
resource "vsphere_distributed_port_group" "k8s_app_pg" {
  name                            = var.k8s_port_group_name
  distributed_virtual_switch_uuid = var.vsphere_distributed_switch_uuid
  vlan_id                         = var.k8s_vlan_id
  number_of_ports                 = var.port_group_ports
  type                            = "earlyBinding"
  allow_promiscuous               = false
  allow_mac_changes               = false
  allow_forged_transmits          = false
}

# 建立高度隔離的 Windows Agent 測試網段 (防嗅探與偽造)。
resource "vsphere_distributed_port_group" "isolated_windows_pg" {
  name                            = var.windows_port_group_name
  distributed_virtual_switch_uuid = var.vsphere_distributed_switch_uuid
  vlan_id                         = var.windows_vlan_id
  number_of_ports                 = var.port_group_ports
  type                            = "earlyBinding"
  allow_promiscuous               = false
  allow_mac_changes               = false
  allow_forged_transmits          = false
}
