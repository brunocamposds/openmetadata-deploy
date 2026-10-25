output "namespace" {
  description = "Namespace onde o OpenMetadata foi instalado"
  value       = kubernetes_namespace.om_namespace.metadata[0].name
}

output "access_instructions" {
  description = "Instruções de acesso aos serviços no host Windows"
  value       = <<EOT
Serviços disponíveis no cluster K3s e host Windows:

1. OpenMetadata UI:
   - Ingress: http://openmetadata.local
   - Direto:  http://localhost:8585 (via make port-forward)
   - Usuário: admin@open-metadata.org
   - Senha: admin

2. ClickHouse Server (DBeaver / Python / SQL):
   - Ingress HTTP: http://clickhouse.local (porta 80)
   - Túnel Direto: http://localhost:8123 (via make port-forward)
   - Database: investments
   - Usuário: clickhouse_user
   - Senha: clickhouse_password

3. MongoDB Serving Layer (MongoDB Compass):
   - Ingress Host: mongodb.local
   - Conexão local: mongodb://localhost:27017 (via make port-forward)
   - Database: investments_serving
   - Collection: rf_customer_positions
EOT
}
