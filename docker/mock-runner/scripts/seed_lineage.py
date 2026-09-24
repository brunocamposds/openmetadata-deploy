"""
Script de Mock: Registro de Grafo de Linhagem de Dados no OpenMetadata.
Cria o fluxo:
raw_crm.users -> staging.stg_crm_users -> customer_mart.dim_customers -> churn_risk_dashboard
"""

import os
import requests
from typing import Dict, Any

OM_URL = os.getenv("OPENMETADATA_SERVER_URL", "http://openmetadata:8585/api").rstrip("/")
JWT_TOKEN = os.getenv("OPENMETADATA_JWT_TOKEN", "")

HEADERS = {
    "Content-Type": "application/json",
}
if JWT_TOKEN:
    HEADERS["Authorization"] = f"Bearer {JWT_TOKEN}"

def api_put(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{OM_URL}/{endpoint}"
    resp = requests.put(url, json=payload, headers=HEADERS, timeout=30)
    if resp.status_code in (200, 201):
        print(f"[SUCCESS] PUT {endpoint} -> {payload.get('name', '')}")
        return resp.json()
    else:
        print(f"[WARN] PUT {endpoint} status {resp.status_code}: {resp.text}")
        return {}

def api_get_by_name(entity_type: str, fqn: str) -> Dict[str, Any]:
    url = f"{OM_URL}/v1/{entity_type}/name/{fqn}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    return resp.json() if resp.status_code == 200 else {}

def add_lineage_edge(from_entity: Dict[str, Any], to_entity: Dict[str, Any]):
    url = f"{OM_URL}/v1/lineage"
    payload = {
        "edge": {
            "fromEntity": {
                "id": from_entity["id"],
                "type": from_entity.get("type", "table")
            },
            "toEntity": {
                "id": to_entity["id"],
                "type": to_entity.get("type", "table")
            }
        }
    }
    resp = requests.put(url, json=payload, headers=HEADERS, timeout=30)
    if resp.status_code in (200, 201):
        print(f"[SUCCESS] Linhagem criada: {from_entity.get('name')} -> {to_entity.get('name')}")
    else:
        print(f"[WARN] Falha ao criar borda de linhagem ({resp.status_code}): {resp.text}")

def main():
    print(f"[*] Iniciando seed de Linhagem no OpenMetadata: {OM_URL}")
    db_service = "local_warehouse"

    # 1. Garantir que Database e Schemas Upstream existam
    api_put("v1/databases", {"name": "raw_db", "service": db_service, "description": "Raw Data Layer"})
    api_put("v1/databaseSchemas", {"name": "crm", "database": f"{db_service}.raw_db", "description": "Raw CRM Data"})

    api_put("v1/databases", {"name": "staging_db", "service": db_service, "description": "Staging Data Layer"})
    api_put("v1/databaseSchemas", {"name": "crm_staging", "database": f"{db_service}.staging_db", "description": "Cleaned CRM Data"})

    # 2. Criar Tabelas
    t_raw = api_put("v1/tables", {
        "name": "raw_users",
        "databaseSchema": f"{db_service}.raw_db.crm",
        "columns": [{"name": "id", "dataType": "VARCHAR"}, {"name": "email", "dataType": "VARCHAR"}, {"name": "created_at", "dataType": "TIMESTAMP"}]
    })

    t_stg = api_put("v1/tables", {
        "name": "stg_crm_users",
        "databaseSchema": f"{db_service}.staging_db.crm_staging",
        "columns": [{"name": "user_id", "dataType": "VARCHAR"}, {"name": "clean_email", "dataType": "VARCHAR"}]
    })

    # 3. Buscar a tabela do Data Product criada anteriormente (dim_customers)
    t_mart = api_get_by_name("tables", f"{db_service}.analytics_dw.customer_mart.dim_customers")

    # 4. Criar Dashboard Service e Dashboard para ponta final da linhagem
    api_put("v1/services/dashboardServices", {
        "name": "metabase_local",
        "serviceType": "Metabase",
        "connection": {"config": {"type": "Metabase", "hostPort": "http://localhost:3000"}}
    })

    dash = api_put("v1/dashboards", {
        "name": "customer_churn_bi",
        "displayName": "Executive Customer Churn Dashboard",
        "service": "metabase_local",
        "description": "Dashboard executivo consumindo o Data Product Customer 360"
    })

    # 5. Conectar o Grafo de Linhagem
    if t_raw.get("id") and t_stg.get("id"):
        add_lineage_edge({"id": t_raw["id"], "type": "table", "name": "raw_users"},
                         {"id": t_stg["id"], "type": "table", "name": "stg_crm_users"})

    if t_stg.get("id") and t_mart.get("id"):
        add_lineage_edge({"id": t_stg["id"], "type": "table", "name": "stg_crm_users"},
                         {"id": t_mart["id"], "type": "table", "name": "dim_customers"})

    if t_mart.get("id") and dash.get("id"):
        add_lineage_edge({"id": t_mart["id"], "type": "table", "name": "dim_customers"},
                         {"id": dash["id"], "type": "dashboard", "name": "customer_churn_bi"})

    print("\n[+] Grafo completo de linhagem registrado com sucesso!")

if __name__ == "__main__":
    main()
