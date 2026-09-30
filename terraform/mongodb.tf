# ==============================================================================
# MongoDB Deployment e Service para Serving Layer
# Exposto via LoadBalancer na porta 27017 para acesso direto via MongoDB Compass
# ==============================================================================

resource "kubernetes_persistent_volume_claim" "mongodb_pvc" {
  metadata {
    name      = "mongodb-data-pvc"
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

resource "kubernetes_deployment" "mongodb" {
  metadata {
    name      = "mongodb"
    namespace = kubernetes_namespace.om_namespace.metadata[0].name
    labels = {
      app = "mongodb"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "mongodb"
      }
    }

    template {
      metadata {
        labels = {
          app = "mongodb"
        }
      }

      spec {
        container {
          name  = "mongodb"
          image = "mongo:7.0"

          port {
            name           = "mongodb"
            container_port = 27017
          }

          volume_mount {
            name       = "mongodb-storage"
            mount_path = "/data/db"
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
          name = "mongodb-storage"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim.mongodb_pvc.metadata[0].name
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "mongodb_service" {
  metadata {
    name      = "mongodb"
    namespace = kubernetes_namespace.om_namespace.metadata[0].name
    labels = {
      app = "mongodb"
    }
  }

  spec {
    type = "LoadBalancer"

    selector = {
      app = "mongodb"
    }

    port {
      name        = "mongodb"
      port        = 27017
      target_port = 27017
    }
  }
}
