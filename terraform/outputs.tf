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

2. DuckDB Server (pg_duckdb - Postgres Protocol):
   - Conexão local (DBeaver / OM): postgresql://duckdb_user:duckdb_password@localhost:5433/investments
   - Conexão interna cluster: postgresql://duckdb_user:duckdb_password@duckdb-server.openmetadata.svc.cluster.local:5432/investments
   - Database: investments
   - Usuário: duckdb_user
   - Senha: duckdb_password

3. DuckDB Web UI (CloudBeaver):
   - URL: http://localhost:8978
   - Conectado ao DuckDB Server via rede

4. MongoDB Serving Layer:
   - Conexão local (Compass / CLI): mongodb://localhost:27017
   - Conexão interna cluster: mongodb://mongodb.openmetadata.svc.cluster.local:27017
   - Database: investments_serving
   - Collection: rf_customer_positions
EOT
}
