output "namespace" {
  description = "Namespace onde o OpenMetadata foi instalado"
  value       = kubernetes_namespace.om_namespace.metadata[0].name
}

output "access_instructions" {
  description = "Instruções de acesso aos serviços no host Windows"
  value       = <<EOT
Serviços disponíveis no cluster K3s e host Windows:

1. OpenMetadata UI:
   - URL: http://localhost (via Traefik Ingress) ou http://localhost:8585
   - Usuário: admin@open-metadata.org
   - Senha: admin

2. ClickHouse Server (Colunar Analítico Nativo):
   - Conexão HTTP (OM / Python / curl): http://localhost:8123 (interno: http://clickhouse-server.openmetadata.svc.cluster.local:8123)
   - Conexão Nativa (TCP): localhost:9000 (interno: clickhouse-server.openmetadata.svc.cluster.local:9000)
   - Database: investments
   - Usuário: clickhouse_user
   - Senha: clickhouse_password

3. ClickHouse Web UI (CloudBeaver):
   - URL: http://localhost:8978
   - Conectado ao ClickHouse Server via JDBC

4. MongoDB Serving Layer:
   - Conexão local (Compass / CLI): mongodb://localhost:27017
   - Conexão interna cluster: mongodb://mongodb.openmetadata.svc.cluster.local:27017
   - Database: investments_serving
   - Collection: rf_customer_positions
EOT
}
