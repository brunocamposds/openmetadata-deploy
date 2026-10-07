# ==============================================================================
# CloudBeaver Web UI para ClickHouse
# Interface Web completa para visualização e execução de queries SQL no ClickHouse
# Acessível via navegador em http://localhost:8978
# ==============================================================================

resource "kubernetes_persistent_volume_claim" "cloudbeaver_workspace_pvc" {
  metadata {
    name      = "cloudbeaver-workspace-pvc"
    namespace = kubernetes_namespace.om_namespace.metadata[0].name
  }

  wait_until_bound = false

  spec {
    access_modes       = ["ReadWriteOnce"]
    storage_class_name = var.storage_class_name

    resources {
      requests = {
        storage = "2Gi"
      }
    }
  }
}

resource "kubernetes_config_map" "cloudbeaver_config" {
  metadata {
    name      = "cloudbeaver-config"
    namespace = kubernetes_namespace.om_namespace.metadata[0].name
    labels = {
      app = "cloudbeaver"
    }
  }

  data = {
    "cloudbeaver.conf" = <<-EOT
    {
        server: {
            serverPort: 8978,
            workspaceLocation: "workspace",
            contentRoot: "web",
            driversLocation: "drivers",
            rootURI: "/",
            serviceURI: "/api/",
            productConfiguration: "conf/product.conf",
            expireSessionAfterPeriod: 1800000,
            develMode: false,
            enableSecurityManager: false,
            database: {
                driver: "h2_embedded_v2",
                url: "jdbc:h2:$${workspace}/.data/cb.h2v2.dat",
                initialDataConfiguration: "conf/initial-data.conf",
                pool: {
                    minIdleConnections: 4,
                    maxIdleConnections: 10,
                    maxConnections: 100,
                    validationQuery: "SELECT 1"
                }
            }
        },
        app: {
            anonymousAccessEnabled: true,
            anonymousUserRole: "admin",
            grantConnectionsAccessToAnonymousTeam: true,
            supportsCustomConnections: true,
            showReadOnlyConnectionInfo: true,
            forwardProxy: false,
            publicCredentialsSaveEnabled: true,
            adminCredentialsSaveEnabled: true,
            resourceManagerEnabled: true,
            resourceQuotas: {
                dataExportFileSizeLimit: 10000000,
                resourceManagerFileSizeLimit: 500000,
                sqlMaxRunningQueries: 100,
                sqlResultSetRowsLimit: 100000,
                sqlResultSetMemoryLimit: 2000000,
                sqlTextPreviewMaxLength: 4096,
                sqlBinaryPreviewMaxLength: 261120
            },
            enabledAuthProviders: [
                "local"
            ],
            disabledDrivers: [
                "sqlite:sqlite_jdbc",
                "h2:h2_embedded",
                "h2:h2_embedded_v2",
                "clickhouse:yandex_clickhouse"
            ]
        }
    }
    EOT

    "initial-data.conf" = <<-EOT
    {
        teams: [
            {
                subjectId: "admin",
                teamName: "Admin",
                description: "Administrative access. Has all permissions.",
                permissions: [ "admin" ]
            },
            {
                subjectId: "user",
                teamName: "User",
                description: "All users, including anonymous.",
                permissions: [ "admin" ]
            }
        ]
    }
    EOT

    "initial-data-sources.conf" = <<-EOT
    {
        "folders": {},
        "connections": {
            "clickhouse-server": {
                "provider": "clickhouse",
                "driver": "com_clickhouse",
                "name": "ClickHouse Server",
                "save-password": true,
                "show-system-objects": true,
                "read-only": false,
                "configuration": {
                    "host": "clickhouse-server",
                    "port": "8123",
                    "database": "investments",
                    "url": "jdbc:clickhouse://clickhouse-server:8123/investments",
                    "user": "clickhouse_user",
                    "password": "clickhouse_password",
                    "type": "dev",
                    "auth-model": "native",
                    "handlers": {}
                }
            }
        }
    }
    EOT

    "data-sources-permissions.json" = <<-EOT
    {
        "clickhouse-server": ["user", "admin"]
    }
    EOT
  }
}

resource "kubernetes_deployment" "cloudbeaver" {
  metadata {
    name      = "cloudbeaver"
    namespace = kubernetes_namespace.om_namespace.metadata[0].name
    labels = {
      app = "cloudbeaver"
    }
  }

  spec {
    replicas = 1

    strategy {
      type = "Recreate"
    }

    selector {
      match_labels = {
        app = "cloudbeaver"
      }
    }

    template {
      metadata {
        labels = {
          app = "cloudbeaver"
        }
      }

      spec {
        init_container {
          name  = "init-cloudbeaver-config"
          image = "busybox:1.36"
          command = [
            "sh",
            "-c",
            "mkdir -p /workspace/GlobalConfiguration/.dbeaver /workspace/.data && cp /config/initial-data-sources.conf /workspace/GlobalConfiguration/.dbeaver/data-sources.json && cp /config/data-sources-permissions.json /workspace/GlobalConfiguration/.dbeaver/data-sources-permissions.json"
          ]

          volume_mount {
            name       = "cloudbeaver-workspace"
            mount_path = "/workspace"
          }

          volume_mount {
            name       = "cloudbeaver-config-vol"
            mount_path = "/config"
          }
        }

        container {
          name  = "cloudbeaver"
          image = "dbeaver/cloudbeaver:24.0.0"

          env {
            name  = "CLOUDBEAVER_APP_GRANT_CONNECTIONS_ACCESS_TO_ANONYMOUS_TEAM"
            value = "true"
          }

          port {
            name           = "http"
            container_port = 8978
          }

          volume_mount {
            name       = "cloudbeaver-workspace"
            mount_path = "/opt/cloudbeaver/workspace"
          }

          volume_mount {
            name       = "cloudbeaver-config-vol"
            mount_path = "/opt/cloudbeaver/conf/cloudbeaver.conf"
            sub_path   = "cloudbeaver.conf"
          }

          volume_mount {
            name       = "cloudbeaver-config-vol"
            mount_path = "/opt/cloudbeaver/conf/initial-data.conf"
            sub_path   = "initial-data.conf"
          }

          volume_mount {
            name       = "cloudbeaver-config-vol"
            mount_path = "/opt/cloudbeaver/conf/initial-data-sources.conf"
            sub_path   = "initial-data-sources.conf"
          }

          volume_mount {
            name       = "cloudbeaver-config-vol"
            mount_path = "/opt/cloudbeaver/conf/data-sources-permissions.json"
            sub_path   = "data-sources-permissions.json"
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
          name = "cloudbeaver-workspace"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim.cloudbeaver_workspace_pvc.metadata[0].name
          }
        }

        volume {
          name = "cloudbeaver-config-vol"
          config_map {
            name = kubernetes_config_map.cloudbeaver_config.metadata[0].name
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "cloudbeaver_service" {
  metadata {
    name      = "cloudbeaver"
    namespace = kubernetes_namespace.om_namespace.metadata[0].name
    labels = {
      app = "cloudbeaver"
    }
  }

  spec {
    type = "LoadBalancer"

    selector = {
      app = "cloudbeaver"
    }

    port {
      name        = "http"
      port        = 8978
      target_port = 8978
    }
  }
}
