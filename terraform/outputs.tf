output "namespace" {
  description = "Namespace onde o OpenMetadata foi instalado"
  value       = kubernetes_namespace.om_namespace.metadata[0].name
}

output "access_instructions" {
  description = "Instruções para acessar a interface web do OpenMetadata no host Windows"
  value       = <<EOT
Para acessar a interface do OpenMetadata no seu navegador (Host Windows):

1. Execute o port-forward no WSL Ubuntu:
   kubectl port-forward svc/openmetadata 8585:8585 -n ${kubernetes_namespace.om_namespace.metadata[0].name}

2. Abra no navegador:
   http://localhost:8585

Usuário padrão inicial: admin@open-metadata.org
Senha padrão inicial: admin
EOT
}

output "mock_runner_instructions" {
  description = "Comando para executar os scripts de mock de Data Products e Linhagem"
  value       = <<EOT
Com o OpenMetadata rodando e acessível na porta 8585:

docker run --rm --net=host -e OPENMETADATA_SERVER_URL="http://localhost:8585/api" om-mock-runner:latest python scripts/seed_data_products.py
docker run --rm --net=host -e OPENMETADATA_SERVER_URL="http://localhost:8585/api" om-mock-runner:latest python scripts/seed_lineage.py
EOT
}
