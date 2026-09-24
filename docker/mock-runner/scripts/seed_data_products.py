"""
Script de Mock: Registro de Domínio, Data Product, Tabelas e Contratos ODCS no OpenMetadata.
"""

import os
import sys
import yaml
import requests
from typing import Dict, Any

# Configurações do servidor OpenMetadata
OM_URL = os.getenv("OPENMETADATA_SERVER_URL", "http://openmetadata:8585/api").rstrip("/")
JWT_TOKEN = os.getenv("OPENMETADATA_JWT_TOKEN", "")

HEADERS = {
    "Content-Type": "application/json",
}
if JWT_TOKEN:
    HEADERS["Authorization"] = f"Bearer {JWT_TOKEN}"

def api_post(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{OM_URL}/{endpoint}"
    resp = requests.post(url, json=payload, headers=HEADERS, timeout=30)
    if resp.status_code in (200, 201):
        print(f"[SUCCESS] POST {endpoint} -> {payload.get('name', '')}")
        return resp.json()
    elif resp.status_code == 409:
        print(f"[EXISTS] {endpoint} -> {payload.get('name', '')}")
        # Fetch existing
        get_resp = requests.get(f"{url}/name/{payload.get('name')}", headers=HEADERS, timeout=30)
        return get_resp.json() if get_resp.status_code == 200 else {}
    else:
        print(f"[WARN] POST {endpoint} retornou status {resp.status_code}: {resp.text}")
        return {}

def api_put(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{OM_URL}/{endpoint}"
    resp = requests.put(url, json=payload, headers=HEADERS, timeout=30)
    if resp.status_code in (200, 201):
        print(f"[SUCCESS] PUT {endpoint} -> {payload.get('name', '')}")
        return resp.json()
    else:
        print(f"[WARN] PUT {endpoint} retornou status {resp.status_code}: {resp.text}")
        return {}

def main():
    print(f"[*] Iniciando seed de produtos de dados no OpenMetadata: {OM_URL}")

    # 1. Carregar Contrato ODCS
    contract_path = os.path.join(os.path.dirname(__file__), "..", "contracts", "sample_customer_contract.odcs.yaml")
    if not os.path.exists(contract_path):
        contract_path = "contracts/sample_customer_contract.odcs.yaml"

    with open(contract_path, "r", encoding="utf-8") as f:
        contract = yaml.safe_load(f)

    # 2. Criar Domínio
    domain_name = "CustomerMarketing"
    domain_payload = {
        "name": domain_name,
        "displayName": "Customer & Marketing",
        "description": "Domínio de negócio responsável por dados de aquisição, engajamento e retenção de clientes.",
        "domainType": "Aggregate"
    }
    domain_obj = api_put("v1/domains", domain_payload)
    domain_id = domain_obj.get("id")

    # 3. Criar Data Product (Marketplace)
    product_name = "Customer360Insights"
    product_payload = {
        "name": product_name,
        "displayName": "Customer 360 & Churn Insights",
        "description": "Produto de dados consolidado com atributos 360 do cliente, métricas de LTV e probabilidade preditiva de churn. Aderente ao padrão ODCS v3.0.",
        "domain": domain_name
    }
    product_obj = api_put("v1/dataProducts", product_payload)

    # 4. Criar Database Service mock (PostgreSQL Warehouse)
    db_service_name = "local_warehouse"
    service_payload = {
        "name": db_service_name,
        "serviceType": "Postgres",
        "connection": {
            "config": {
                "type": "Postgres",
                "scheme": "postgresql+psycopg2",
                "authType": {
                    "username": "openmetadata_user",
                    "password": "password"
                },
                "hostPort": "postgresql:5432",
                "database": "analytics_dw"
            }
        }
    }
    api_put("v1/services/databaseServices", service_payload)

    # 5. Criar Database
    db_payload = {
        "name": "analytics_dw",
        "service": db_service_name,
        "description": "Data Warehouse Analítico de Produção"
    }
    api_put("v1/databases", db_payload)

    # 6. Criar Database Schema
    schema_payload = {
        "name": "customer_mart",
        "database": f"{db_service_name}.analytics_dw",
        "description": "Data Mart especializado em clientes e métricas de negócios"
    }
    api_put("v1/databaseSchemas", schema_payload)

    # 7. Criar Tabela 'dim_customers' derivada do Contrato ODCS
    columns = []
    for col in contract.get("schema", []):
        col_type = col.get("type", "VARCHAR").upper()
        if "STRING" in col_type:
            data_type = "VARCHAR"
        elif "DECIMAL" in col_type or "NUMERIC" in col_type:
            data_type = "NUMERIC"
        elif "TIMESTAMP" in col_type:
            data_type = "TIMESTAMP"
        else:
            data_type = "VARCHAR"

        columns.append({
            "name": col.get("name"),
            "dataType": data_type,
            "description": col.get("description", ""),
            "tags": [{"tagFQN": f"PersonalData.{tag}", "labelType": "Manual", "state": "Suggested"} for tag in col.get("tags", []) if "pii" in tag.lower()]
        })

    table_payload = {
        "name": "dim_customers",
        "databaseSchema": f"{db_service_name}.analytics_dw.customer_mart",
        "description": f"Tabela associada ao Contrato ODCS: {contract.get('info', {}).get('title')}. {contract.get('info', {}).get('description')}",
        "columns": columns,
        "tableType": "Regular",
        "domain": domain_name
    }
    table_obj = api_put("v1/tables", table_payload)
    table_id = table_obj.get("id")

    # 8. Vincular a Tabela como um ativo do Data Product
    if table_id and product_obj.get("id"):
        patch_payload = [
            {
                "op": "add",
                "path": "/assets/0",
                "value": {
                    "id": table_id,
                    "type": "table"
                }
            }
        ]
        headers_patch = HEADERS.copy()
        headers_patch["Content-Type"] = "application/json-patch+json"
        patch_url = f"{OM_URL}/v1/dataProducts/{product_obj.get('id')}"
        resp_patch = requests.patch(patch_url, json=patch_payload, headers=headers_patch, timeout=30)
        if resp_patch.status_code in (200, 201):
            print(f"[SUCCESS] Tabela dim_customers vinculada ao Data Product '{product_name}'")
        else:
            print(f"[INFO] Patch data product: {resp_patch.status_code}")

    print("\n[+] Seed de Domínios, Data Products e Contratos concluído com sucesso!")

if __name__ == "__main__":
    main()
