variable "vsphere_user" {
  description = "Username for the vSphere API."
  type        = string
}

variable "vsphere_password" {
  description = "Password for the vSphere API."
  type        = string
  sensitive   = true
}

variable "vsphere_server" {
  description = "Hostname or IP address of the vSphere API endpoint."
  type        = string
}

variable "vsphere_distributed_switch_uuid" {
  description = "UUID of the existing vSphere distributed virtual switch that owns the port groups."
  type        = string
}

variable "vsphere_allow_unverified_ssl" {
  description = "Allow TLS without verifying the vSphere server certificate."
  type        = bool
  default     = false
}

variable "k8s_port_group_name" {
  description = "Name of the Kubernetes application port group."
  type        = string
  default     = "VLAN-20-K8s-App"
}

variable "k8s_vlan_id" {
  description = "VLAN ID for the Kubernetes application network."
  type        = number
  default     = 20
}

variable "windows_port_group_name" {
  description = "Name of the isolated Windows test port group."
  type        = string
  default     = "VLAN-100-Windows-Isolated"
}

variable "windows_vlan_id" {
  description = "VLAN ID for the isolated Windows test network."
  type        = number
  default     = 100
}

variable "port_group_ports" {
  description = "Number of preallocated ports for each distributed port group."
  type        = number
  default     = 32
}
