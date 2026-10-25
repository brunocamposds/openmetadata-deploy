# Makefile de automação para deploy do OpenMetadata no K3s (WSL Ubuntu)

.PHONY: init plan apply destroy port-forward deploy-cdb deploy-cra deploy-derivado deploy-all status stop pause start build-runner job-cdb job-cra job-derivado job-status job-logs-cdb job-logs-cra job-logs-derivado reset help

help:
	@echo "Comandos disponíveis:"
	@echo "  --- Infraestrutura & Cluster ---"
	@echo "  make init             - Inicializa o Terraform e providers"
	@echo "  make plan             - Gera plano de execução do Terraform"
	@echo "  make apply            - Aplica todos os recursos (OpenMetadata, ClickHouse Server, MongoDB)"
	@echo "  make status           - Verifica os pods, serviços, PVCs e Ingress no namespace openmetadata"
	@echo "  make stop             - Hiberna os serviços (0% CPU/RAM) preservando os dados"
	@echo "  make start            - Retoma todos os serviços rapidamente com dados salvos"
	@echo "  make port-forward     - Abre túneis para OpenMetadata (:8585), ClickHouse (:8123) e MongoDB (:27017)"
	@echo "  make reset            - Limpa todo o catálogo do OM, ClickHouse e MongoDB (volta ao estado recém-instalado)"
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
	kubectl apply -f manifests/traefik-config.yaml
	cd terraform && terraform apply -auto-approve
	kubectl apply -f manifests/traefik-routes.yaml

deploy: apply

status:
	kubectl get pods,svc,pvc,ingressroutes,ingressroutetcps -n openmetadata

stop:
	@echo "Pausando todos os serviços (liberando RAM/CPU sem perder dados)..."
	kubectl scale deployment openmetadata --replicas=0 -n openmetadata
	kubectl scale deployment clickhouse-server --replicas=0 -n openmetadata
	kubectl scale deployment mongodb --replicas=0 -n openmetadata
	@echo "Aguardando término das aplicações antes de desligar os bancos..."
	@kubectl wait --namespace openmetadata --for=delete pod -l app.kubernetes.io/name=openmetadata --timeout=30s || true
	kubectl scale statefulset opensearch --replicas=0 -n openmetadata
	kubectl scale statefulset postgresql --replicas=0 -n openmetadata
	@echo "Ambiente pausado com sucesso!"

pause: stop

start:
	@echo "Iniciando bases de dados e dependências..."
	kubectl scale statefulset postgresql --replicas=1 -n openmetadata
	kubectl scale statefulset opensearch --replicas=1 -n openmetadata
	kubectl scale deployment mongodb --replicas=1 -n openmetadata
	kubectl scale deployment clickhouse-server --replicas=1 -n openmetadata
	@echo "Aguardando PostgreSQL e OpenSearch..."
	@kubectl wait --namespace openmetadata --for=condition=ready pod -l app.kubernetes.io/name=postgresql --timeout=300s
	@kubectl wait --namespace openmetadata --for=condition=ready pod -l app.kubernetes.io/name=opensearch --timeout=300s
	@echo "Iniciando OpenMetadata Server..."
	kubectl scale deployment openmetadata --replicas=1 -n openmetadata
	@echo "Aguardando OpenMetadata estar pronto (execução de migrações e índices de busca no OpenSearch pode levar até 15 minutos)..."
	@kubectl wait --namespace openmetadata --for=condition=ready pod -l app.kubernetes.io/name=openmetadata --timeout=1800s
	@echo "=================================================="
	@echo "Serviços prontos para uso via Traefik (SEM necessidade de port-forward):"
	@echo "  - OpenMetadata UI & REST API:"
	@echo "      • http://localhost/ (Porta 80 padrão Traefik)"
	@echo "      • http://localhost:8585"
	@echo "      • http://openmetadata.local (via hosts)"
	@echo "  - ClickHouse Server:"
	@echo "      • HTTP / REST: http://localhost:8123 ou http://clickhouse.local"
	@echo "      • Native TCP:  localhost:9000 (DBeaver / Clients)"
	@echo "  - MongoDB (Serving Layer):"
	@echo "      • Protocolo Binário TCP: mongodb://localhost:27017 (Compass / Drivers)"
	@echo "  - PostgreSQL (Catálogo):"
	@echo "      • PostgreSQL TCP: localhost:5432"
	@echo "=================================================="

port-forward:
	@echo "AVISO: O cluster utiliza Traefik como Ingress/Proxy L4-L7 e todos os serviços"
	@echo "já estão expostos diretamente em localhost sem necessidade deste comando!"
	@echo "=================================================="
	@echo "Túneis locais adicionais (Ctrl+C para encerrar):"
	@echo "  - OpenMetadata UI:   http://localhost:8585"
	@echo "  - ClickHouse Server: http://localhost:8123 (DBeaver)"
	@echo "  - MongoDB Compass:   mongodb://localhost:27017"
	@echo "Credenciais:"
	@echo "  - OM: admin@open-metadata.org / admin"
	@echo "  - ClickHouse: clickhouse_user / clickhouse_password (Database: investments)"
	@echo "=================================================="
	@trap 'kill 0' EXIT; \
	kubectl port-forward svc/openmetadata 8585:8585 -n openmetadata & \
	kubectl port-forward svc/clickhouse-server 8123:8123 -n openmetadata & \
	kubectl port-forward svc/mongodb 27017:27017 -n openmetadata & \
	wait

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
	docker build -t pipeline-runner:latest -t duckdb-pipeline-runner:latest docker/pipeline-runner

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

reset:
	@echo "Executando limpeza completa do catálogo do OpenMetadata e bancos de dados..."
	python3 -u scripts/reset_openmetadata.py

destroy:
	cd terraform && terraform destroy -auto-approve
