# 使用 Helm Provider 來安裝數據層，這比純 YAML 更容易維護版本
provider "helm" {
  kubernetes {
    config_path = "~/.kube/config"
  }
}

resource "helm_release" "mongodb" {
  name       = "mongodb-firmware"
  repository = "https://charts.bitnami.com/bitnami"
  chart      = "mongodb"
  namespace  = "xdr-soar"

  set {
    name  = "persistence.size"
    value = "200Gi" # 稍後討論的資源分配
  }
}