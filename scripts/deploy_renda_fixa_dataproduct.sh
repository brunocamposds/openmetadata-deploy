#!/usr/bin/env bash
# ==============================================================================
# Script de Automação CI/CD / DataOps:
# Cadastro Interativo de Produto de Dados (Renda Fixa) no OpenMetadata via REST API
# Baseado nos padrões ODPS (Open Data Product Standard) e ODCS (Open Data Contract Standard)
# ==============================================================================

set -eo pipefail

# Paleta de Cores para Terminal
BOLD="\033[1m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[1;33m"
BLUE="\033[0;34m"
MAGENTA="\033[0;35m"
RED="\033[0;31m"
RESET="\033[0m"

# Configurações do OpenMetadata
OM_API_URL="${OPENMETADATA_SERVER_URL:-http://localhost:8585/api}"
OM_WEB_URL="${OPENMETADATA_WEB_URL:-http://localhost:8585}"
OM_ADMIN_EMAIL="${OPENMETADATA_ADMIN_EMAIL:-admin@open-metadata.org}"
OM_ADMIN_PASSWORD="${OPENMETADATA_ADMIN_PASSWORD:-admin}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

ODPS_FILE="${BASE_DIR}/contracts/odps/renda_fixa.odps.yaml"
ODCS_FILE="${BASE_DIR}/contracts/odcs/posicao_renda_fixa.odcs.yaml"

echo -e "${BOLD}${MAGENTA}==============================================================================${RESET}"
echo -e "${BOLD}${MAGENTA}   OpenMetadata: Cadastro Interativo de Data Product (Renda Fixa)           ${RESET}"
echo -e "${BOLD}${MAGENTA}   Pipeline CI/CD 100% via API REST com Contratos ODPS & ODCS                ${RESET}"
echo -e "${BOLD}${MAGENTA}==============================================================================${RESET}\n"

# ------------------------------------------------------------------------------
# Funções Auxiliares
# ------------------------------------------------------------------------------

pause_step() {
    local step_title="$1"
    local link="$2"

    echo -e "\n${BOLD}${GREEN}✔ ${step_title} concluída com sucesso!${RESET}"
    if [ -n "$link" ]; then
        echo -e "${BOLD}${CYAN}🔗 Acesse no OpenMetadata:${RESET} ${BOLD}${YELLOW}${link}${RESET}"
    fi
    echo -e "${BLUE}------------------------------------------------------------------------------${RESET}"
    if [ "${AUTO_APPROVE:-false}" != "true" ]; then
        read -r -p "Pressione [ENTER] para avançar para a próxima etapa..." _
    else
        echo -e "${YELLOW}[AUTO_APPROVE] Prosseguindo automaticamente...${RESET}"
    fi
    echo ""
}

api_call() {
    local method="$1"
    local endpoint="$2"
    local data="${3:-}"
    local content_type="${4:-application/json}"

    local url="${OM_API_URL}/${endpoint}"
    
    if [ -n "$data" ]; then
        curl -s -X "${method}" \
             -H "Authorization: Bearer ${JWT_TOKEN}" \
             -H "Content-Type: ${content_type}" \
             -d "${data}" \
             "${url}"
    else
        curl -s -X "${method}" \
             -H "Authorization: Bearer ${JWT_TOKEN}" \
             "${url}"
    fi
}

# ------------------------------------------------------------------------------
# Etapa 0: Autenticação na API do OpenMetadata
# ------------------------------------------------------------------------------
echo -e "${BOLD}${BLUE}[Etapa 0] Autenticação na API do OpenMetadata...${RESET}"

B64_PASS=$(echo -n "${OM_ADMIN_PASSWORD}" | base64)

AUTH_PAYLOAD=$(cat <<EOF
{"email":"${OM_ADMIN_EMAIL}","password":"${B64_PASS}"}
EOF
)

AUTH_RESP=$(curl -s -X POST -H "Content-Type: application/json" -d "${AUTH_PAYLOAD}" "${OM_API_URL}/v1/users/login")
JWT_TOKEN=$(echo "${AUTH_RESP}" | jq -r '.accessToken // empty')

if [ -z "${JWT_TOKEN}" ]; then
    echo -e "${RED}Erro: Não foi possível autenticar no OpenMetadata em ${OM_API_URL}${RESET}"
    echo -e "${RED}Resposta da API: ${AUTH_RESP}${RESET}"
    exit 1
fi

echo -e "${GREEN}Autenticação bem-sucedida! JWT Token obtido.${RESET}"
echo -e "${BLUE}Contratos carregados:${RESET}"
echo -e "  - ODPS: ${ODPS_FILE}"
echo -e "  - ODCS: ${ODCS_FILE}\n"

# ------------------------------------------------------------------------------
# Etapa 1: Criação do Time Proprietário (Squad Renda Fixa)
# ------------------------------------------------------------------------------
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
echo -e "${BOLD}${CYAN}[Etapa 1] Criando Time Proprietário: squad-renda-fixa...${RESET}"
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"

TEAM_PAYLOAD=$(cat <<EOF
{
  "name": "squad-renda-fixa",
  "displayName": "Squad Renda Fixa",
  "description": "Time responsável pelos produtos de dados analíticos e operacionais de Renda Fixa (CDB, CRA, Debêntures).",
  "teamType": "Group"
}
EOF
)

TEAM_RESP=$(api_call "PUT" "v1/teams" "${TEAM_PAYLOAD}")
TEAM_ID=$(echo "${TEAM_RESP}" | jq -r '.id')
echo -e "Time registrado como Group. ID: ${BOLD}${TEAM_ID}${RESET}"

pause_step "Etapa 1: Time squad-renda-fixa" "${OM_WEB_URL}/settings/members/teams/squad-renda-fixa"

# ------------------------------------------------------------------------------
# Etapa 2: Domínio e Subdomínio de Negócio
# ------------------------------------------------------------------------------
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
echo -e "${BOLD}${CYAN}[Etapa 2] Criando Domínio 'Serviços Financeiros' e Subdomínio 'Renda Fixa'...${RESET}"
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"

DOMAIN_PAYLOAD=$(cat <<EOF
{
  "name": "ServicosFinanceiros",
  "displayName": "Serviços Financeiros",
  "description": "Domínio corporativo que engloba operações financeiras, produtos bancários e mercado de capitais.",
  "domainType": "Aggregate"
}
EOF
)
DOMAIN_RESP=$(api_call "PUT" "v1/domains" "${DOMAIN_PAYLOAD}")

SUBDOMAIN_PAYLOAD=$(cat <<EOF
{
  "name": "RendaFixa",
  "displayName": "Renda Fixa",
  "description": "Subdomínio responsável por títulos públicos, bancários e de securitização (CDB, CRA, CRI, LCI, LCA).",
  "domainType": "Source-aligned",
  "parent": "ServicosFinanceiros"
}
EOF
)
SUBDOMAIN_RESP=$(api_call "PUT" "v1/domains" "${SUBDOMAIN_PAYLOAD}")
echo -e "Domínio e Subdomínio registrados."

pause_step "Etapa 2: Domínio e Subdomínio de Negócio" "${OM_WEB_URL}/domain/ServicosFinanceiros.RendaFixa"

# ------------------------------------------------------------------------------
# Etapa 3: Glossário & Conceitos de Negócio
# ------------------------------------------------------------------------------
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
echo -e "${BOLD}${CYAN}[Etapa 3] Criando Glossário e Termos de Negócio de Renda Fixa...${RESET}"
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"

GLOSSARY_PAYLOAD=$(cat <<EOF
{
  "name": "GlossarioRendaFixa",
  "displayName": "Glossário de Renda Fixa",
  "description": "Conceitos padronizados, nomenclaturas e regras de negócio para produtos de Renda Fixa.",
  "domains": ["ServicosFinanceiros.RendaFixa"]
}
EOF
)
GLOSSARY_RESP=$(api_call "PUT" "v1/glossaries" "${GLOSSARY_PAYLOAD}")

# Termo 1: CDB
api_call "PUT" "v1/glossaryTerms" "$(cat <<EOF
{
  "name": "CDB",
  "displayName": "Certificado de Depósito Bancário",
  "description": "Título de renda fixa privado emitido por instituições financeiras bancárias para captação de recursos.",
  "glossary": "GlossarioRendaFixa"
}
EOF
)" > /dev/null

# Termo 2: CRA
api_call "PUT" "v1/glossaryTerms" "$(cat <<EOF
{
  "name": "CRA",
  "displayName": "Certificado de Recebíveis do Agronegócio",
  "description": "Título securitizado lastreado em recebíveis originados no agronegócio, isento de IR para pessoas físicas.",
  "glossary": "GlossarioRendaFixa"
}
EOF
)" > /dev/null

# Termo 3: Saldo Líquido
api_call "PUT" "v1/glossaryTerms" "$(cat <<EOF
{
  "name": "SaldoLiquido",
  "displayName": "Saldo Líquido em Custódia",
  "description": "Valor líquido projetado para resgate do cliente após dedução de IRRF, IOF e taxas de custódia.",
  "glossary": "GlossarioRendaFixa"
}
EOF
)" > /dev/null

# Termo 4: Preço Unitário (PU)
api_call "PUT" "v1/glossaryTerms" "$(cat <<EOF
{
  "name": "PrecoUnitario",
  "displayName": "Preço Unitário (PU)",
  "description": "Cotação unitária do título na data de marcação a mercado ou na curva de emissão.",
  "glossary": "GlossarioRendaFixa"
}
EOF
)" > /dev/null

pause_step "Etapa 3: Glossário de Renda Fixa" "${OM_WEB_URL}/glossary/GlossarioRendaFixa"

# ------------------------------------------------------------------------------
# Etapa 4: Sistemas de Origem (Mainframe DB2 - CDB1 & SQL Server - CRA1)
# ------------------------------------------------------------------------------
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
echo -e "${BOLD}${CYAN}[Etapa 4] Registrando Sistemas de Origem (Mainframe DB2 e SQL Server)...${RESET}"
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"

# 4.1 Mainframe DB2 (CDB1)
api_call "PUT" "v1/services/databaseServices" "$(cat <<EOF
{
  "name": "mainframe_db2_cdb1",
  "serviceType": "Db2",
  "description": "Mainframe IBM z/OS DB2 - Sistema Core Bancário de Emissão e Boletagem de CDBs (CDB1)",
  "connection": {
    "config": {
      "type": "Db2",
      "scheme": "db2+ibm_db",
      "hostPort": "mainframe.corp.local:50000",
      "database": "CDB1_PROD"
    }
  }
}
EOF
)" > /dev/null

api_call "PUT" "v1/databases" "$(cat <<EOF
{
  "name": "CDB1_PROD",
  "service": "mainframe_db2_cdb1",
  "description": "Banco de dados transacional de CDBs"
}
EOF
)" > /dev/null

api_call "PUT" "v1/databaseSchemas" "$(cat <<EOF
{
  "name": "OPER",
  "database": "mainframe_db2_cdb1.CDB1_PROD",
  "description": "Schema de operações financeiras transacionais"
}
EOF
)" > /dev/null

api_call "PUT" "v1/tables" "$(cat <<EOF
{
  "name": "TB_CDB_OPERACAO",
  "databaseSchema": "mainframe_db2_cdb1.CDB1_PROD.OPER",
  "description": "Tabela transacional contendo registros brutos de emissões de CDB no Mainframe.",
  "columns": [
    {"name": "ID_OPER", "dataType": "VARCHAR", "dataLength": 50, "description": "Identificador da boleta no Mainframe"},
    {"name": "CD_CDB", "dataType": "VARCHAR", "dataLength": 50, "description": "Código do papel CDB"},
    {"name": "NR_CPF", "dataType": "VARCHAR", "dataLength": 14, "description": "Documento do investidor", "tags": [{"tagFQN": "PersonalData.Personal", "labelType": "Manual", "state": "Confirmed"}]},
    {"name": "DT_OPER", "dataType": "DATE", "description": "Data de liquidação"},
    {"name": "VL_OPER", "dataType": "NUMERIC", "description": "Valor financeiro investido"},
    {"name": "TX_CONTR", "dataType": "NUMERIC", "description": "Taxa do CDB"}
  ]
}
EOF
)" > /dev/null

# 4.2 SQL Server (CRA1)
api_call "PUT" "v1/services/databaseServices" "$(cat <<EOF
{
  "name": "sqlserver_cra1",
  "serviceType": "Mssql",
  "description": "Microsoft SQL Server - Sistema Especializado de Securitização de Agronegócio (CRA1)",
  "connection": {
    "config": {
      "type": "Mssql",
      "scheme": "mssql+pyodbc",
      "hostPort": "sqlserver.corp.local:1433",
      "database": "CRA1_PROD"
    }
  }
}
EOF
)" > /dev/null

api_call "PUT" "v1/databases" "$(cat <<EOF
{
  "name": "CRA1_PROD",
  "service": "sqlserver_cra1",
  "description": "Banco de dados transacional de CRAs"
}
EOF
)" > /dev/null

api_call "PUT" "v1/databaseSchemas" "$(cat <<EOF
{
  "name": "dbo",
  "database": "sqlserver_cra1.CRA1_PROD",
  "description": "Schema padrão de custódia e emissões"
}
EOF
)" > /dev/null

api_call "PUT" "v1/tables" "$(cat <<EOF
{
  "name": "tb_cra_operacao",
  "databaseSchema": "sqlserver_cra1.CRA1_PROD.dbo",
  "description": "Tabela transacional de contratos de securitização e títulos de CRA.",
  "columns": [
    {"name": "id_cra", "dataType": "VARCHAR", "dataLength": 50, "description": "ID sequencial da operação CRA"},
    {"name": "cod_cra", "dataType": "VARCHAR", "dataLength": 50, "description": "Código do certificado de recebíveis"},
    {"name": "cpf_investidor", "dataType": "VARCHAR", "dataLength": 14, "description": "CPF do cliente", "tags": [{"tagFQN": "PersonalData.Personal", "labelType": "Manual", "state": "Confirmed"}]},
    {"name": "data_compra", "dataType": "DATE", "description": "Data de alocação"},
    {"name": "valor_nominal", "dataType": "NUMERIC", "description": "Valor nominal alocado"},
    {"name": "taxa_emissao", "dataType": "NUMERIC", "description": "Taxa acordada na emissão"}
  ]
}
EOF
)" > /dev/null

pause_step "Etapa 4: Sistemas de Origem (DB2 e SQL Server)" "${OM_WEB_URL}/table/mainframe_db2_cdb1.CDB1_PROD.OPER.TB_CDB_OPERACAO"

# ------------------------------------------------------------------------------
# Etapa 5: Azure Databricks (Unity Catalog) - Bronze, Silver e Gold
# ------------------------------------------------------------------------------
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
echo -e "${BOLD}${CYAN}[Etapa 5] Criando Databricks Unity Catalog, Camadas Bronze, Silver e Gold...${RESET}"
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"

# Serviço Databricks
api_call "PUT" "v1/services/databaseServices" "$(cat <<EOF
{
  "name": "azure_databricks_uc",
  "serviceType": "Databricks",
  "description": "Lakehouse Corporativo Azure Databricks gerenciado pelo Unity Catalog.",
  "connection": {
    "config": {
      "type": "Databricks",
      "hostPort": "adb-corp.azuredatabricks.net:443",
      "httpPath": "/sql/1.0/endpoints/finance_cluster"
    }
  }
}
EOF
)" > /dev/null

# Catalog no Unity Catalog
api_call "PUT" "v1/databases" "$(cat <<EOF
{
  "name": "finance_catalog",
  "service": "azure_databricks_uc",
  "description": "Catálogo do Unity Catalog dedicado à diretoria financeira e investimentos."
}
EOF
)" > /dev/null

# Schemas nas camadas
for schema in "bronze_cdb1" "bronze_cra1" "silver_cdb1" "silver_cra1" "silver_renda_fixa" "gold_renda_fixa"; do
    api_call "PUT" "v1/databaseSchemas" "$(cat <<EOF
{
  "name": "${schema}",
  "database": "azure_databricks_uc.finance_catalog",
  "description": "Schema da camada ${schema} no Unity Catalog",
  "domains": ["ServicosFinanceiros.RendaFixa"]
}
EOF
)" > /dev/null
done

# Tabelas Bronze
api_call "PUT" "v1/tables" "$(cat <<EOF
{
  "name": "raw_operacoes_cdb",
  "databaseSchema": "azure_databricks_uc.finance_catalog.bronze_cdb1",
  "description": "Camada Bronze: Ingestão raw periódica da tabela TB_CDB_OPERACAO do Mainframe.",
  "domains": ["ServicosFinanceiros.RendaFixa"],
  "columns": [
    {"name": "ID_OPER", "dataType": "VARCHAR", "dataLength": 50},
    {"name": "CD_CDB", "dataType": "VARCHAR", "dataLength": 50},
    {"name": "NR_CPF", "dataType": "VARCHAR", "dataLength": 14},
    {"name": "DT_OPER", "dataType": "DATE"},
    {"name": "VL_OPER", "dataType": "NUMERIC"},
    {"name": "TX_CONTR", "dataType": "NUMERIC"},
    {"name": "_ingested_at", "dataType": "TIMESTAMP"}
  ]
}
EOF
)" > /dev/null

api_call "PUT" "v1/tables" "$(cat <<EOF
{
  "name": "raw_operacoes_cra",
  "databaseSchema": "azure_databricks_uc.finance_catalog.bronze_cra1",
  "description": "Camada Bronze: Ingestão raw periódica da tabela tb_cra_operacao do SQL Server.",
  "domains": ["ServicosFinanceiros.RendaFixa"],
  "columns": [
    {"name": "id_cra", "dataType": "VARCHAR", "dataLength": 50},
    {"name": "cod_cra", "dataType": "VARCHAR", "dataLength": 50},
    {"name": "cpf_investidor", "dataType": "VARCHAR", "dataLength": 14},
    {"name": "data_compra", "dataType": "DATE"},
    {"name": "valor_nominal", "dataType": "NUMERIC"},
    {"name": "taxa_emissao", "dataType": "NUMERIC"},
    {"name": "_ingested_at", "dataType": "TIMESTAMP"}
  ]
}
EOF
)" > /dev/null

# Tabelas Silver Source-Aligned
api_call "PUT" "v1/tables" "$(cat <<EOF
{
  "name": "posicao_cdb",
  "databaseSchema": "azure_databricks_uc.finance_catalog.silver_cdb1",
  "description": "Camada Silver Source-Aligned: Posições tratadas e padronizadas do sistema CDB1.",
  "domains": ["ServicosFinanceiros.RendaFixa"],
  "columns": [
    {"name": "id_operacao", "dataType": "VARCHAR", "dataLength": 50},
    {"name": "codigo_instrumento", "dataType": "VARCHAR", "dataLength": 50},
    {"name": "cpf_cliente", "dataType": "VARCHAR", "dataLength": 14},
    {"name": "data_emissao", "dataType": "DATE"},
    {"name": "taxa_contratada", "dataType": "NUMERIC"},
    {"name": "saldo_bruto", "dataType": "NUMERIC"},
    {"name": "saldo_liquido", "dataType": "NUMERIC"}
  ]
}
EOF
)" > /dev/null

api_call "PUT" "v1/tables" "$(cat <<EOF
{
  "name": "posicao_cra",
  "databaseSchema": "azure_databricks_uc.finance_catalog.silver_cra1",
  "description": "Camada Silver Source-Aligned: Posições tratadas e padronizadas do sistema CRA1.",
  "domains": ["ServicosFinanceiros.RendaFixa"],
  "columns": [
    {"name": "id_operacao", "dataType": "VARCHAR", "dataLength": 50},
    {"name": "codigo_instrumento", "dataType": "VARCHAR", "dataLength": 50},
    {"name": "cpf_cliente", "dataType": "VARCHAR", "dataLength": 14},
    {"name": "data_emissao", "dataType": "DATE"},
    {"name": "taxa_contratada", "dataType": "NUMERIC"},
    {"name": "saldo_bruto", "dataType": "NUMERIC"},
    {"name": "saldo_liquido", "dataType": "NUMERIC"}
  ]
}
EOF
)" > /dev/null

# Tabela Silver Derived Data Product (posicao_consolidada) - Extraída do Contrato ODCS
COLUMNS_JSON=$(python3 -c "
import yaml, json
with open('${ODCS_FILE}') as f:
    contract = yaml.safe_load(f)
cols = []
for c in contract.get('schema', []):
    dtype = c.get('dataType', 'VARCHAR')
    col = {
        'name': c['name'],
        'dataType': dtype,
        'description': c.get('description', '')
    }
    if dtype in ['VARCHAR', 'CHAR', 'BINARY', 'VARBINARY']:
        col['dataLength'] = c.get('dataLength', 255)
    if c.get('classification'):
        col['tags'] = [{'tagFQN': 'PersonalData.Personal', 'labelType': 'Manual', 'state': 'Confirmed'}]
    cols.append(col)
print(json.dumps(cols))
")

TABLE_ODCS_PAYLOAD=$(cat <<EOF
{
  "name": "posicao_consolidada",
  "databaseSchema": "azure_databricks_uc.finance_catalog.silver_renda_fixa",
  "description": "Derived Data Product de Renda Fixa: Posição consolidada multissistema (CDB + CRA) padronizada conforme Contrato ODCS v3.0.",
  "domains": ["ServicosFinanceiros.RendaFixa"],
  "columns": ${COLUMNS_JSON}
}
EOF
)
T_DERIVED_RESP=$(api_call "PUT" "v1/tables" "${TABLE_ODCS_PAYLOAD}")
T_DERIVED_ID=$(echo "${T_DERIVED_RESP}" | jq -r '.id // empty')
if [ -z "${T_DERIVED_ID}" ]; then
    T_DERIVED_ID=$(curl -s -H "Authorization: Bearer ${JWT_TOKEN}" "${OM_API_URL}/v1/tables/name/azure_databricks_uc.finance_catalog.silver_renda_fixa.posicao_consolidada" | jq -r '.id // empty')
fi

# Tabela Gold Sumarizada (custodia_liquida_consolidada)
api_call "PUT" "v1/tables" "$(cat <<EOF
{
  "name": "custodia_liquida_consolidada",
  "databaseSchema": "azure_databricks_uc.finance_catalog.gold_renda_fixa",
  "description": "Camada Gold: Agregações diárias e saldos líquidos consolidados em custódia por instrumento, emissor e faixa de cliente.",
  "domains": ["ServicosFinanceiros.RendaFixa"],
  "columns": [
    {"name": "data_referencia", "dataType": "DATE"},
    {"name": "tipo_instrumento", "dataType": "VARCHAR", "dataLength": 20},
    {"name": "total_clientes_ativos", "dataType": "INT"},
    {"name": "total_saldo_bruto_custodia", "dataType": "NUMERIC"},
    {"name": "total_saldo_liquido_custodia", "dataType": "NUMERIC"},
    {"name": "pu_medio_ponderado", "dataType": "NUMERIC"}
  ]
}
EOF
)" > /dev/null

pause_step "Etapa 5: Databricks Unity Catalog e Tabelas" "${OM_WEB_URL}/table/azure_databricks_uc.finance_catalog.silver_renda_fixa.posicao_consolidada"

# ------------------------------------------------------------------------------
# Etapa 6: Porta de Saída Operacional (MongoDB - Canal Mobile)
# ------------------------------------------------------------------------------
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
echo -e "${BOLD}${CYAN}[Etapa 6] Criando Serviço de Saída MongoDB (Canal Mobile)...${RESET}"
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"

api_call "PUT" "v1/services/databaseServices" "$(cat <<EOF
{
  "name": "mongodb_mobile",
  "serviceType": "MongoDB",
  "description": "Cluster MongoDB operacional que alimenta a camada BFF dos aplicativos mobile de clientes.",
  "connection": {
    "config": {
      "type": "MongoDB",
      "hostPort": "mongodb-cluster.internal:27017"
    }
  }
}
EOF
)" > /dev/null

api_call "PUT" "v1/databases" "$(cat <<EOF
{
  "name": "mobile_db",
  "service": "mongodb_mobile",
  "description": "Database de consumo da esteira mobile"
}
EOF
)" > /dev/null

api_call "PUT" "v1/databaseSchemas" "$(cat <<EOF
{
  "name": "collections",
  "database": "mongodb_mobile.mobile_db",
  "description": "Coleções ativas para cache mobile"
}
EOF
)" > /dev/null

api_call "PUT" "v1/tables" "$(cat <<EOF
{
  "name": "posicao_cliente",
  "databaseSchema": "mongodb_mobile.mobile_db.collections",
  "description": "Coleção MongoDB com payload desnormalizado da posição de renda fixa consumida em sub-segundos pelo app mobile.",
  "columns": [
    {"name": "_id", "dataType": "VARCHAR", "dataLength": 100},
    {"name": "cpf_cliente", "dataType": "VARCHAR", "dataLength": 14, "tags": [{"tagFQN": "PersonalData.Personal", "labelType": "Manual", "state": "Confirmed"}]},
    {"name": "resumo_renda_fixa", "dataType": "JSON"},
    {"name": "total_liquido_custodia", "dataType": "NUMERIC"},
    {"name": "ultima_atualizacao", "dataType": "TIMESTAMP"}
  ]
}
EOF
)" > /dev/null

pause_step "Etapa 6: Porta de Saída MongoDB Mobile" "${OM_WEB_URL}/table/mongodb_mobile.mobile_db.collections.posicao_cliente"

# ------------------------------------------------------------------------------
# Etapa 7: Registro do Data Product no Marketplace (ODPS)
# ------------------------------------------------------------------------------
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
echo -e "${BOLD}${CYAN}[Etapa 7] Registrando Data Product 'RendaFixaConsolidada' extraído do ODPS...${RESET}"
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"

DP_INFO=$(python3 -c "
import yaml, json
with open('${ODPS_FILE}') as f:
    odps = yaml.safe_load(f)
print(json.dumps({
    'name': odps.get('name'),
    'displayName': odps.get('displayName'),
    'description': odps.get('info', {}).get('description')
}))
")

DP_NAME=$(echo "${DP_INFO}" | jq -r '.name')
DP_DISPLAY=$(echo "${DP_INFO}" | jq -r '.displayName')
DP_DESC=$(echo "${DP_INFO}" | jq -r '.description')

DP_PAYLOAD=$(cat <<EOF
{
  "name": "${DP_NAME}",
  "displayName": "${DP_DISPLAY}",
  "description": "${DP_DESC}",
  "dataProductType": "DERIVED_DATA",
  "domains": ["ServicosFinanceiros.RendaFixa"],
  "owners": [
    {
      "id": "${TEAM_ID}",
      "type": "team"
    }
  ],
  "assets": [
    {
      "id": "${T_DERIVED_ID}",
      "type": "table"
    }
  ]
}
EOF
)

DP_RESP=$(api_call "PUT" "v1/dataProducts" "${DP_PAYLOAD}")
DP_ID=$(echo "${DP_RESP}" | jq -r '.id // empty')
if [ -z "${DP_ID}" ]; then
    DP_ID=$(curl -s -H "Authorization: Bearer ${JWT_TOKEN}" "${OM_API_URL}/v1/dataProducts/name/${DP_NAME}" | jq -r '.id // empty')
fi
echo -e "Data Product criado com sucesso. ID: ${BOLD}${DP_ID}${RESET}"
echo -e "Ativo central (posicao_consolidada: ${T_DERIVED_ID}) vinculado ao Data Product!"

pause_step "Etapa 7: Data Product Renda Fixa no Marketplace" "${OM_WEB_URL}/dataProducts/ServicosFinanceiros.RendaFixa.${DP_NAME}"

# ------------------------------------------------------------------------------
# Etapa 8: Registro da Linhagem Ponta a Ponta
# ------------------------------------------------------------------------------
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
echo -e "${BOLD}${CYAN}[Etapa 8] Construindo Grafo de Linhagem Ponta a Ponta...${RESET}"
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"

add_edge() {
    local from_fqn="$1"
    local to_fqn="$2"

    local from_obj=$(curl -s -H "Authorization: Bearer ${JWT_TOKEN}" "${OM_API_URL}/v1/tables/name/${from_fqn}")
    local to_obj=$(curl -s -H "Authorization: Bearer ${JWT_TOKEN}" "${OM_API_URL}/v1/tables/name/${to_fqn}")

    local from_id=$(echo "${from_obj}" | jq -r '.id // empty')
    local to_id=$(echo "${to_obj}" | jq -r '.id // empty')

    if [ -n "${from_id}" ] && [ -n "${to_id}" ]; then
        local edge_payload=$(cat <<EOF
{
  "edge": {
    "fromEntity": {"id": "${from_id}", "type": "table"},
    "toEntity": {"id": "${to_id}", "type": "table"}
  }
}
EOF
        )
        api_call "PUT" "v1/lineage" "${edge_payload}" > /dev/null
        echo -e "  🔗 ${GREEN}${from_fqn}${RESET} ➔ ${GREEN}${to_fqn}${RESET}"
    else
        echo -e "  ${YELLOW}Aviso: Não foi possível obter IDs para ${from_fqn} (${from_id}) -> ${to_fqn} (${to_id})${RESET}"
    fi
}

echo -e "Conectando o fluxo de dados:"
# 1. Mainframe -> Bronze CDB
add_edge "mainframe_db2_cdb1.CDB1_PROD.OPER.TB_CDB_OPERACAO" "azure_databricks_uc.finance_catalog.bronze_cdb1.raw_operacoes_cdb"

# 2. Bronze CDB -> Silver CDB
add_edge "azure_databricks_uc.finance_catalog.bronze_cdb1.raw_operacoes_cdb" "azure_databricks_uc.finance_catalog.silver_cdb1.posicao_cdb"

# 3. SQL Server -> Bronze CRA
add_edge "sqlserver_cra1.CRA1_PROD.dbo.tb_cra_operacao" "azure_databricks_uc.finance_catalog.bronze_cra1.raw_operacoes_cra"

# 4. Bronze CRA -> Silver CRA
add_edge "azure_databricks_uc.finance_catalog.bronze_cra1.raw_operacoes_cra" "azure_databricks_uc.finance_catalog.silver_cra1.posicao_cra"

# 5. Silver CDB & CRA -> Derived Data Product (posicao_consolidada)
add_edge "azure_databricks_uc.finance_catalog.silver_cdb1.posicao_cdb" "azure_databricks_uc.finance_catalog.silver_renda_fixa.posicao_consolidada"
add_edge "azure_databricks_uc.finance_catalog.silver_cra1.posicao_cra" "azure_databricks_uc.finance_catalog.silver_renda_fixa.posicao_consolidada"

# 6. Derived Data Product -> Gold Custódia Sumarizada
add_edge "azure_databricks_uc.finance_catalog.silver_renda_fixa.posicao_consolidada" "azure_databricks_uc.finance_catalog.gold_renda_fixa.custodia_liquida_consolidada"

# 7. Derived Data Product -> Output Port MongoDB Mobile
add_edge "azure_databricks_uc.finance_catalog.silver_renda_fixa.posicao_consolidada" "mongodb_mobile.mobile_db.collections.posicao_cliente"

pause_step "Etapa 8: Linhagem Ponta a Ponta Registrada" "${OM_WEB_URL}/table/azure_databricks_uc.finance_catalog.silver_renda_fixa.posicao_consolidada/lineage"

# ------------------------------------------------------------------------------
# Conclusão
# ------------------------------------------------------------------------------
echo -e "${BOLD}${GREEN}==============================================================================${RESET}"
echo -e "${BOLD}${GREEN}   PRODUTO DE DADOS DE RENDA FIXA REGISTRADO COM SUCESSO!                   ${RESET}"
echo -e "${BOLD}${GREEN}==============================================================================${RESET}"
echo -e "\n${BOLD}Resumo do que foi criado via API:${RESET}"
echo -e " 1. Time Responsável:      ${YELLOW}squad-renda-fixa${RESET}"
echo -e " 2. Domínio e Subdomínio:   ${YELLOW}ServicosFinanceiros -> RendaFixa${RESET}"
echo -e " 3. Glossário & Termos:    ${YELLOW}GlossarioRendaFixa (CDB, CRA, PU, etc.)${RESET}"
echo -e " 4. Origens Legadas:       ${YELLOW}Mainframe DB2 (CDB1) e SQL Server (CRA1)${RESET}"
echo -e " 5. Lakehouse Databricks:  ${YELLOW}Unity Catalog: Bronze, Silver Source-Aligned, Silver Derived e Gold${RESET}"
echo -e " 6. Output Port Mobile:    ${YELLOW}MongoDB (mobile_db.posicao_cliente)${RESET}"
echo -e " 7. Data Product ODPS:     ${YELLOW}RendaFixaConsolidada com contrato ODCS vinculado${RESET}"
echo -e " 8. Grafo de Linhagem:     ${YELLOW}Completo, desde as origens transacionais até a camada mobile${RESET}\n"

echo -e "${CYAN}Link Principal do Data Product:${RESET} ${BOLD}${YELLOW}${OM_WEB_URL}/dataProducts/ServicosFinanceiros.RendaFixa.${DP_NAME}${RESET}"
echo -e "${CYAN}Link da Linhagem Ponta a Ponta:${RESET} ${BOLD}${YELLOW}${OM_WEB_URL}/table/azure_databricks_uc.finance_catalog.silver_renda_fixa.posicao_consolidada/lineage${RESET}\n"
