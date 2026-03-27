output "k8s_port_group_name" {
  description = "Name of the Kubernetes application distributed port group."
  value       = vsphere_distributed_port_group.k8s_app_pg.name
}

output "k8s_port_group_vlan" {
  description = "VLAN ID for the Kubernetes application distributed port group."
  value       = vsphere_distributed_port_group.k8s_app_pg.vlan_id
}

output "windows_port_group_name" {
  description = "Name of the isolated Windows distributed port group."
  value       = vsphere_distributed_port_group.isolated_windows_pg.name
}

output "windows_port_group_vlan" {
  description = "VLAN ID for the isolated Windows distributed port group."
  value       = vsphere_distributed_port_group.isolated_windows_pg.vlan_id
}
