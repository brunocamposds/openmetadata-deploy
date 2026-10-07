# ==============================================================================
# ClickHouse Server - Banco de Dados Colunar de Alta Performance (K3s)
# Conector nativo de primeira classe no OpenMetadata (serviceType: Clickhouse)
# Acessível internamente e externamente nas portas 8123 (HTTP) e 9000 (Native)
# ==============================================================================

resource "kubernetes_persistent_volume_claim" "clickhouse_server_pvc" {
  metadata {
    name      = "clickhouse-server-data-pvc"
    namespace = kubernetes_namespace.om_namespace.metadata[0].name
  }

  wait_until_bound = false

  spec {
    access_modes       = ["ReadWriteOnce"]
    storage_class_name = var.storage_class_name

    resources {
      requests = {
        storage = "5Gi"
      }
    }
  }
}

resource "kubernetes_deployment" "clickhouse_server" {
  metadata {
    name      = "clickhouse-server"
    namespace = kubernetes_namespace.om_namespace.metadata[0].name
    labels = {
      app = "clickhouse-server"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "clickhouse-server"
      }
    }

    template {
      metadata {
        labels = {
          app = "clickhouse-server"
        }
      }

      spec {
        container {
          name  = "clickhouse-server"
          image = "clickhouse/clickhouse-server:24.3-alpine"

          port {
            name           = "http"
            container_port = 8123
          }

          port {
            name           = "native"
            container_port = 9000
          }

          env {
            name  = "CLICKHOUSE_DB"
            value = "investments"
          }

          env {
            name  = "CLICKHOUSE_USER"
            value = "clickhouse_user"
          }

          env {
            name  = "CLICKHOUSE_PASSWORD"
            value = "clickhouse_password"
          }

          env {
            name  = "CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT"
            value = "1"
          }

          volume_mount {
            name       = "clickhouse-storage"
            mount_path = "/var/lib/clickhouse"
          }

          resources {
            limits = {
              cpu    = "1"
              memory = "1Gi"
            }
            requests = {
              cpu    = "100m"
              memory = "256Mi"
            }
          }
        }

        volume {
          name = "clickhouse-storage"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim.clickhouse_server_pvc.metadata[0].name
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "clickhouse_server_service" {
  metadata {
    name      = "clickhouse-server"
    namespace = kubernetes_namespace.om_namespace.metadata[0].name
    labels = {
      app = "clickhouse-server"
    }
  }

  spec {
    type = "LoadBalancer"

    selector = {
      app = "clickhouse-server"
    }

    port {
      name        = "http"
      port        = 8123
      target_port = 8123
    }

    port {
      name        = "native"
      port        = 9000
      target_port = 9000
    }
  }
}
