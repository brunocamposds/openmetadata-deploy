# Makefile de automação para deploy do OpenMetadata no K3s (WSL Ubuntu)

.PHONY: init plan apply destroy port-forward deploy-cdb deploy-cra deploy-derivado deploy-all status stop start build-runner job-cdb job-cra job-derivado job-status job-logs-cdb job-logs-cra job-logs-derivado help

help:
	@echo "Comandos disponíveis:"
	@echo "  --- Infraestrutura & Cluster ---"
	@echo "  make init             - Inicializa o Terraform e providers"
	@echo "  make plan             - Gera plano de execução do Terraform"
	@echo "  make apply            - Aplica todos os recursos (OpenMetadata, DuckDB Server, CloudBeaver, MongoDB)"
	@echo "  make status           - Verifica os pods, serviços, PVCs e Ingress no namespace openmetadata"
	@echo "  make stop             - Hiberna os serviços (0% CPU/RAM) preservando os dados"
	@echo "  make start            - Retoma todos os serviços rapidamente com dados salvos"
	@echo "  make port-forward     - Abre túnel para acessar http://localhost:8585 no navegador"
	@echo "  make destroy          - Remove os recursos criados pelo Terraform"
	@echo ""
	@echo "  --- Governança as Code (Marketplace & Contratos no OpenMetadata) ---"
	@echo "  make deploy-cdb       - Registra o Data Product SIST_CDB no OpenMetadata"
	@echo "  make deploy-cra       - Registra o Data Product SIST_CRA no OpenMetadata"
	@echo "  make deploy-derivado  - Registra o Data Product RENDA_FIXA_DERIVADO no OpenMetadata"
	@echo "  make deploy-all       - Executa o deploy dos 3 produtos de dados em sequência"
	@echo ""
	@echo "  --- Pipelines de Dados (Execução 100% via Jobs no K3s) ---"
	@echo "  make build-runner     - Constrói a imagem duckdb-pipeline-runner:latest para os jobs"
	@echo "  make job-cdb          - Dispara o Job K3s do SIST_CDB (CSV -> Bronze -> Silver -> DQ)"
	@echo "  make job-cra          - Dispara o Job K3s do SIST_CRA (CSV -> Bronze -> Silver -> DQ)"
	@echo "  make job-derivado     - Dispara o Job K3s de RENDA_FIXA_DERIVADO (Consolidação -> Gold -> Mongo -> DQ)"
	@echo "  make job-status       - Lista os Jobs e Pods de execução no cluster"
	@echo "  make job-logs-cdb     - Exibe os logs do Job do SIST_CDB"
	@echo "  make job-logs-cra     - Exibe os logs do Job do SIST_CRA"
	@echo "  make job-logs-derivado- Exibe os logs do Job de Renda Fixa Derivado"

init:
	cd terraform && terraform init

plan:
	cd terraform && terraform plan

apply:
	cd terraform && terraform apply -auto-approve
	kubectl apply -f manifests/openmetadata-ingress.yaml

status:
	kubectl get pods,svc,pvc,ingress -n openmetadata

stop:
	@echo "Pausando todos os serviços (liberando RAM/CPU sem perder dados)..."
	kubectl scale deployment openmetadata --replicas=0 -n openmetadata
	kubectl scale deployment cloudbeaver --replicas=0 -n openmetadata
	kubectl scale deployment duckdb-server --replicas=0 -n openmetadata
	kubectl scale deployment mongodb --replicas=0 -n openmetadata
	kubectl scale statefulset opensearch --replicas=0 -n openmetadata
	kubectl scale statefulset postgresql --replicas=0 -n openmetadata
	@echo "Ambiente pausado com sucesso!"

start:
	@echo "Iniciando todos os serviços a partir do estado salvo..."
	kubectl scale statefulset postgresql --replicas=1 -n openmetadata
	kubectl scale statefulset opensearch --replicas=1 -n openmetadata
	kubectl scale deployment openmetadata --replicas=1 -n openmetadata
	kubectl scale deployment mongodb --replicas=1 -n openmetadata
	kubectl scale deployment duckdb-server --replicas=1 -n openmetadata
	kubectl scale deployment cloudbeaver --replicas=1 -n openmetadata
	@echo "Aguardando OpenMetadata estar pronto..."
	@kubectl wait --namespace openmetadata --for=condition=ready pod -l app.kubernetes.io/name=openmetadata --timeout=300s
	@echo "=================================================="
	@echo "Serviços prontos para uso:"
	@echo "  - OpenMetadata UI: http://localhost"
	@echo "  - DuckDB Web UI:   http://localhost:8978"
	@echo "  - MongoDB Compass: mongodb://localhost:27017"
	@echo "  - DuckDB Server:   localhost:5433"
	@echo "=================================================="

port-forward:
	@echo "Aguardando o pod do OpenMetadata estar totalmente inicializado (Running/Ready)..."
	@kubectl wait --namespace openmetadata --for=condition=ready pod -l app.kubernetes.io/name=openmetadata --timeout=1800s
	@echo "=================================================="
	@echo "Acesse no navegador: http://localhost:8585"
	@echo "Credenciais de acesso inicial:"
	@echo "  Email: admin@open-metadata.org"
	@echo "  Senha: admin"
	@echo "=================================================="

deploy-cdb:
	./scripts/deploy_repo_product.sh repos/sist-cdb

deploy-cra:
	./scripts/deploy_repo_product.sh repos/sist-cra

deploy-derivado:
	./scripts/deploy_repo_product.sh repos/renda-fixa-derivado

deploy-all: deploy-cdb deploy-cra deploy-derivado

approve-cdb:
	./scripts/approve_repo_product.sh repos/sist-cdb

approve-cra:
	./scripts/approve_repo_product.sh repos/sist-cra

approve-derivado:
	./scripts/approve_repo_product.sh repos/renda-fixa-derivado

approve-all: approve-cdb approve-cra approve-derivado

build-runner:
	docker build -t duckdb-pipeline-runner:latest docker/pipeline-runner

job-cdb:
	@echo "Disparando Job K3s: SIST_CDB..."
	kubectl delete job pipeline-cdb -n openmetadata --ignore-not-found=true
	kubectl apply -f repos/sist-cdb/k8s/job-cdb.yaml

job-cra:
	@echo "Disparando Job K3s: SIST_CRA..."
	kubectl delete job pipeline-cra -n openmetadata --ignore-not-found=true
	kubectl apply -f repos/sist-cra/k8s/job-cra.yaml

job-derivado:
	@echo "Disparando Job K3s: RENDA_FIXA_DERIVADO..."
	kubectl delete job pipeline-renda-fixa -n openmetadata --ignore-not-found=true
	kubectl apply -f repos/renda-fixa-derivado/k8s/job-renda-fixa.yaml

job-status:
	kubectl get jobs,pods -l 'app in (pipeline-cdb, pipeline-cra, pipeline-renda-fixa)' -n openmetadata

job-logs-cdb:
	kubectl logs -l app=pipeline-cdb -n openmetadata --tail=50 -f

job-logs-cra:
	kubectl logs -l app=pipeline-cra -n openmetadata --tail=50 -f

job-logs-derivado:
	kubectl logs -l app=pipeline-renda-fixa -n openmetadata --tail=50 -f

destroy:
	cd terraform && terraform destroy -auto-approve
