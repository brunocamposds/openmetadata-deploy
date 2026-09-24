# Makefile de automação para deploy do OpenMetadata no K3s (WSL Ubuntu)

.PHONY: init plan apply destroy port-forward build-mock seed-products seed-lineage seed-renda-fixa status help

help:
	@echo "Comandos disponíveis:"
	@echo "  make init             - Inicializa o Terraform e providers"
	@echo "  make plan             - Gera plano de execução do Terraform"
	@echo "  make apply            - Aplica os recursos no K3s (Postgres, OpenSearch, OpenMetadata)"
	@echo "  make status           - Verifica os pods e serviços no namespace openmetadata"
	@echo "  make port-forward     - Abre túnel para acessar http://localhost:8585 no navegador"
	@echo "  make seed-renda-fixa  - Executa o laboratório interativo de Data Product Renda Fixa (ODPS/ODCS)"
	@echo "  make build-mock       - Constrói a imagem Docker do runner de mocks e contratos"
	@echo "  make seed-products    - Executa o mock de Data Products e Contratos ODCS"
	@echo "  make seed-lineage     - Executa o mock de linhagem ponta a ponta"
	@echo "  make destroy          - Remove os recursos criados pelo Terraform"

init:
	cd terraform && terraform init

plan:
	cd terraform && terraform plan

apply:
	cd terraform && terraform apply -auto-approve

status:
	kubectl get pods,svc,pvc -n openmetadata

port-forward:
	@echo "Acesse no navegador: http://localhost:8585"
	@echo "Credenciais de acesso inicial:"
	@echo "  Email: admin@open-metadata.org"
	@echo "  Senha: admin"
	@echo "--------------------------------------------------"
	kubectl port-forward svc/openmetadata 8585:8585 -n openmetadata

seed-renda-fixa:
	./scripts/deploy_renda_fixa_dataproduct.sh

build-mock:
	docker build -t om-mock-runner:latest docker/mock-runner

seed-products:
	docker run --rm --net=host -e OPENMETADATA_SERVER_URL="http://localhost:8585/api" om-mock-runner:latest python scripts/seed_data_products.py

seed-lineage:
	docker run --rm --net=host -e OPENMETADATA_SERVER_URL="http://localhost:8585/api" om-mock-runner:latest python scripts/seed_lineage.py

destroy:
	cd terraform && terraform destroy -auto-approve

