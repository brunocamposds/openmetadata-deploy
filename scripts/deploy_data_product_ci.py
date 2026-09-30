#!/usr/bin/env python3
"""
==============================================================================
OpenMetadata CI/CD Pipeline - Governance as Code Engine
==============================================================================
Realiza o parse estrito dos manifestos ODPS (v1.0.0) e contratos ODCS (v3.0.0)
de qualquer repositório e sincroniza de forma idempotente com a API REST
do OpenMetadata.

Suporta:
- Criação/atualização de Domínio, Subdomínio e Teams
- Registro de Database Services (Databricks Unity Catalog, MongoDB Atlas, Origens)
- Mapeamento estrito de Tabelas e Colunas com Tipos, Constraints e Tags PII
- Registro do Data Product no Marketplace com seus Assets vinculados
- Resolução e conexão automática de dependências e linhagem (Lineage)
- Links diretos clicáveis para validação no navegador
==============================================================================
"""

import sys
import os
import re
import json
import base64
import argparse
from pathlib import Path
import yaml
import csv
import time
import requests

# Cores ANSI para saída no terminal
BOLD = "\033[1m"
GREEN = "\033[0;32m"
CYAN = "\033[0;36m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
MAGENTA = "\033[0;35m"
RED = "\033[0;31m"
RESET = "\033[0m"


def sanitize_name(val: str) -> str:
    """Sanitiza strings removendo acentos e caracteres especiais para identificadores válidos no OpenMetadata."""
    rep = {
        'ã': 'a', 'á': 'a', 'à': 'a', 'â': 'a',
        'õ': 'o', 'ó': 'o', 'ô': 'o',
        'é': 'e', 'ê': 'e',
        'í': 'i', 'ú': 'u',
        'ç': 'c', ' ': ''
    }
    cleaned = val
    for k, v in rep.items():
        cleaned = cleaned.replace(k, v).replace(k.upper(), v.upper())
    return re.sub(r'[^a-zA-Z0-9_\-]', '', cleaned)


class OpenMetadataClient:
    def __init__(self, base_url: str, email: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api"
        self.email = email
        self.password = password
        self.token = None
        self.headers = {"Content-Type": "application/json"}
        self._authenticate()

    def _authenticate(self):
        b64_pass = base64.b64encode(self.password.encode()).decode()
        login_url = f"{self.api_url}/v1/users/login"
        payload = {"email": self.email, "password": b64_pass}
        resp = requests.post(login_url, json=payload, timeout=20)
        if resp.status_code != 200:
            raise RuntimeError(f"Falha na autenticação com OpenMetadata ({resp.status_code}): {resp.text}")
        self.token = resp.json()["accessToken"]
        self.headers["Authorization"] = f"Bearer {self.token}"

    def put(self, endpoint: str, payload: dict) -> dict:
        url = f"{self.api_url}/{endpoint}"
        resp = requests.put(url, headers=self.headers, json=payload, timeout=120)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Erro PUT {endpoint} ({resp.status_code}): {resp.text}")
        if resp.text and resp.text.strip():
            try:
                return resp.json()
            except Exception:
                return {}
        return {}

    def get(self, endpoint: str) -> dict:
        url = f"{self.api_url}/{endpoint}"
        resp = requests.get(url, headers=self.headers, timeout=120)
        if resp.status_code == 200:
            return resp.json()
        return {}

    def put_yaml(self, endpoint: str, yaml_content: str) -> dict:
        url = f"{self.api_url}/{endpoint}"
        headers = dict(self.headers)
        headers["Content-Type"] = "application/yaml"
        resp = requests.put(url, headers=headers, data=yaml_content.encode("utf-8"), timeout=120)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Erro PUT YAML {endpoint} ({resp.status_code}): {resp.text}")
        if resp.text and resp.text.strip():
            try:
                return resp.json()
            except Exception:
                return {}
        return {}

    def patch(self, endpoint: str, operations: list) -> dict:
        url = f"{self.api_url}/{endpoint}"
        headers = dict(self.headers)
        headers["Content-Type"] = "application/json-patch+json"
        resp = requests.patch(url, headers=headers, json=operations, timeout=120)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Erro PATCH {endpoint} ({resp.status_code}): {resp.text}")
        if resp.text and resp.text.strip():
            try:
                return resp.json()
            except Exception:
                return {}
        return {}

    def delete(self, endpoint: str) -> bool:
        url = f"{self.api_url}/{endpoint}"
        resp = requests.delete(url, headers=self.headers, timeout=120)
        return resp.status_code in (200, 204)

    def ensure_observability_alert(self):
        """Garante que a Subscription de Alerta de Observabilidade no Activity Feed para Admins existe e está ativa."""
        payload = {
            "name": "DataQualityObservabilityAlert",
            "displayName": "Data Quality Observability Alerts",
            "description": "Dispara alertas e notificacoes no Activity Feed dos administradores quando um teste ODCS falha",
            "alertType": "Observability",
            "enabled": True,
            "resources": ["testCase"],
            "destinations": [
                {
                    "category": "Admins",
                    "type": "ActivityFeed",
                    "enabled": True
                }
            ],
            "input": {
                "filters": [],
                "actions": [
                    {
                        "name": "GetTestCaseStatusUpdates",
                        "effect": "include",
                        "prefixCondition": "AND",
                        "arguments": [
                            {
                                "name": "testResultList",
                                "input": ["Failed"]
                            }
                        ]
                    }
                ]
            }
        }
        try:
            self.put("v1/events/subscriptions", payload)
            print(f"  {GREEN}✔ Observability Alert Subscription ativa: DataQualityObservabilityAlert{RESET}")
        except Exception as e:
            print(f"  {YELLOW}Aviso: Nao foi possivel registrar o alerta de observabilidade: {e}{RESET}")



def extract_iso_retention(odcs_data: dict, odps_data: dict) -> str:
    """Extrai período de retenção dos contratos ODCS/ODPS e formata como ISO-8601 (ex: P5Y)."""
    sl_ret = odcs_data.get("servicelevels", {}).get("retention", {}).get("period")
    if sl_ret:
        digits = "".join([c for c in str(sl_ret) if c.isdigit()])
        if digits:
            return f"P{digits}Y"
    gov_years = odps_data.get("governance", {}).get("retentionYears")
    if gov_years:
        return f"P{gov_years}Y"
    return "P5Y"


def get_layer_and_cert(table_name: str) -> tuple[str, str]:
    """Retorna a classificação de Camada (Tier) e Certificação correspondente."""
    t_lower = table_name.lower()
    if "gold" in t_lower:
        return ("Tier.Tier1", "Certification.Gold")
    elif "bronze" in t_lower or "inbound" in t_lower or "raw" in t_lower:
        return ("Tier.Tier3", "Certification.Bronze")
    else:
        return ("Tier.Tier2", "Certification.Silver")


def build_om_odcs_yaml(odcs_data: dict, table_name: str, full_table_fqn: str, dp_name: str, domain_name: str, status: str = "draft") -> str:
    """Converte o contrato ODCS para a especificação aceita pela API nativa /dataContracts/odcs/yaml do OpenMetadata."""
    om_odcs = {
        "apiVersion": "v3.0.0",
        "kind": "DataContract",
        "id": odcs_data.get("id"),
        "name": odcs_data.get("info", {}).get("title", odcs_data.get("id")),
        "version": str(odcs_data.get("info", {}).get("version", "1.0.0")),
        "status": status,
        "domain": domain_name,
        "dataProduct": dp_name,
        "description": {
            "purpose": odcs_data.get("info", {}).get("description", "").strip()
        }
    }
    schema_objs = []
    models = odcs_data.get("models", [])
    for m in models:
        elements = []
        for col in m.get("columns", []):
            elements.append({
                "name": col.get("name"),
                "physicalName": col.get("name"),
                "physicalType": col.get("physicalType", "STRING"),
                "description": col.get("description", ""),
                "required": not col.get("nullable", True)
            })
        schema_objs.append({
            "name": m.get("table", "").split(".")[-1],
            "physicalName": full_table_fqn,
            "description": m.get("description", ""),
            "properties": elements
        })
    om_odcs["schema"] = schema_objs

    qualities = []
    for q in odcs_data.get("quality", []):
        q_type = q.get("type", "custom")
        if q_type not in ("text", "library", "sql", "custom"):
            q_type = "custom"
        rule_val = q.get("rule", "")
        if not rule_val and "maxAgeHours" in q:
            rule_val = f"maxAgeHours <= {q['maxAgeHours']}"
        qualities.append({
            "type": q_type,
            "name": q.get("name"),
            "description": q.get("description", ""),
            "rule": rule_val
        })
    if qualities:
        om_odcs["quality"] = qualities

    sl = odcs_data.get("servicelevels", {})
    if sl:
        sla_props = []
        if "retention" in sl:
            period_str = str(sl["retention"].get("period", "5 years")).lower()
            val = "".join([c for c in period_str if c.isdigit()]) or "5"
            unit = "year" if ("year" in period_str or "ano" in period_str) else "day"
            sla_props.append({
                "property": "retention",
                "value": val,
                "unit": unit,
                "driver": "regulatory"
            })
        if sla_props:
            om_odcs["slaProperties"] = sla_props

    return yaml.dump(om_odcs, sort_keys=False, allow_unicode=True)



def map_odcs_type_to_om(logical_type: str, physical_type: str = "") -> str:
    """Mapeia os tipos lógicos e físicos do ODCS para o tipo suportado pelo OpenMetadata."""
    phys = (physical_type or "").upper()
    log = (logical_type or "").lower()

    if "DECIMAL" in phys or "NUMERIC" in phys or log in ("decimal", "numeric"):
        return "NUMERIC"
    if "INT" in phys or log in ("int", "integer"):
        return "INT"
    if "BIGINT" in phys or log in ("bigint", "long"):
        return "BIGINT"
    if "DOUBLE" in phys or "FLOAT" in phys or log in ("double", "float"):
        return "DOUBLE"
    if "DATE" in phys or log == "date":
        return "DATE"
    if "TIMESTAMP" in phys or log in ("timestamp", "datetime"):
        return "TIMESTAMP"
    if "BOOLEAN" in phys or log == "boolean":
        return "BOOLEAN"
    if "JSON" in phys or "DOCUMENT" in phys or log in ("json", "object", "array"):
        return "JSON"
    return "VARCHAR"


def humanize_glossary_term(name: str) -> str:
    known = {
        "IdentificadorPosicao": "Identificador da Posição",
        "DataPosicao": "Data da Posição",
        "CertificadoCDB": "Certificado de Depósito Bancário (CDB)",
        "CertificadoCRA": "Certificado de Recebíveis do Agronegócio (CRA)",
        "ClienteTitular": "Código do Cliente Titular",
        "PrincipalAplicado": "Valor Principal Aplicado",
        "SaldoBruto": "Saldo Bruto Consolidado",
        "SaldoLiquido": "Saldo Líquido Estimado",
        "IdentificadorMovimentacao": "Identificador da Movimentação",
        "DataMovimentacao": "Data da Movimentação",
        "TipoMovimentacao": "Tipo de Movimentação Financeira",
        "ValorMovimentado": "Valor da Movimentação",
        "TipoProdutoRendaFixa": "Tipo de Produto de Renda Fixa",
        "SaldoInvestidoTotal": "Saldo Investido Total",
        "TotalAportes": "Total de Aportes Financeiros",
        "TotalResgates": "Total de Resgates Financeiros",
    }
    if name in known:
        return known[name]
    return re.sub(r'([a-z])([A-Z])', r'\1 \2', name)


def provision_glossary_and_terms(client: OpenMetadataClient, repo_path: Path):
    """
    Provisiona o Glossário de Negócio e seus Termos a partir dos contratos ODCS do repositório.
    Garante que os termos apareçam no menu 'Governar -> Glossários' do OpenMetadata.
    """
    print(f"\n{BOLD}{CYAN}>>> [Etapa 3.1] Provisionando Glossário de Negócios e Termos de Governança...{RESET}")
    glossary_name = "Investimentos"
    glossary_payload = {
        "name": glossary_name,
        "displayName": "Glossário de Investimentos",
        "description": "Glossário corporativo de termos conceituais, métricas e entidades de negócio para o domínio de Investimentos.",
        "mutuallyExclusive": False
    }
    client.put("v1/glossaries", glossary_payload)
    print(f"  {GREEN}✔ Glossário Corporativo: {glossary_name}{RESET}")

    terms_found = {}
    for contract_file in (repo_path / "contracts").glob("*.odcs.yaml"):
        try:
            with open(contract_file, "r", encoding="utf-8") as f:
                y = yaml.safe_load(f)
            for model in y.get("models", []):
                for col in model.get("columns", []):
                    bg_term = col.get("businessGlossaryTerm")
                    if bg_term:
                        term_name = bg_term.split(".")[-1]
                        desc = col.get("description", f"Termo de negócio {term_name} para {col.get('name')}.")
                        if term_name not in terms_found:
                            terms_found[term_name] = desc
        except Exception as e:
            print(f"  {YELLOW}Aviso ao ler {contract_file} para glossário: {e}{RESET}")

    for term_name, desc in sorted(terms_found.items()):
        disp_name = humanize_glossary_term(term_name)
        term_payload = {
            "name": term_name,
            "displayName": disp_name,
            "description": desc,
            "glossary": glossary_name
        }
        client.put("v1/glossaryTerms", term_payload)
        print(f"  {GREEN}✔ Termo de Glossário: {glossary_name}.{term_name} ({disp_name}){RESET}")


def deploy_repository_product(repo_path_str: str, client: OpenMetadataClient):
    repo_path = Path(repo_path_str).resolve()
    odps_file = repo_path / "data-product.odps.yaml"

    if not odps_file.exists():
        raise FileNotFoundError(f"Arquivo ODPS não encontrado em: {odps_file}")

    print(f"\n{BOLD}{MAGENTA}{'='*80}{RESET}")
    print(f"{BOLD}{MAGENTA}   OpenMetadata CI/CD Pipeline - Governance as Code                         {RESET}")
    print(f"{BOLD}{MAGENTA}   Deploy de Produto de Dados via Contratos ODPS & ODCS                     {RESET}")
    print(f"{BLUE}Repositório:{RESET} {BOLD}{repo_path}{RESET}")

    # 0. Alertas de Observabilidade
    print(f"\n{BOLD}{CYAN}>>> [Etapa 0] Verificando Regras de Alerta de Observabilidade (Data Quality)...{RESET}")
    client.ensure_observability_alert()

    print(f"{BLUE}Manifesto ODPS:{RESET} {odps_file.name}")

    # 1. Carregar ODPS
    with open(odps_file, "r", encoding="utf-8") as f:
        odps = yaml.safe_load(f)

    product_details = odps.get("product", {}).get("details", {}).get("en", {})
    dp_id = odps.get("id") or product_details.get("productID")
    dp_name = odps.get("name") or product_details.get("name")
    dp_version = odps.get("version") or product_details.get("version", "1.0.0")
    domain_name = odps.get("domain", "Investimentos")
    subdomain_raw = odps.get("subDomain", "Geral")
    subdomain_name = sanitize_name(subdomain_raw)
    dp_desc = (odps.get("description") or product_details.get("description", "")).strip()

    team_data = odps.get("team", {})
    team_name = team_data.get("id", "squad-default")
    team_display = team_data.get("name", team_name)
    team_email = team_data.get("email", f"{team_name}@empresa.com.br")

    print(f"\n{BOLD}{CYAN}>>> [Etapa 1] Registrando Domínio e Subdomínio...{RESET}")
    # Criar Domínio Principal
    client.put("v1/domains", {
        "name": domain_name,
        "displayName": domain_name,
        "description": f"Domínio Corporativo de {domain_name}",
        "domainType": "Aggregate"
    })
    # Criar Subdomínio
    full_domain_fqn = f"{domain_name}.{subdomain_name}"
    client.put("v1/domains", {
        "name": subdomain_name,
        "displayName": subdomain_raw,
        "description": f"Subdomínio de {subdomain_raw} pertencente ao domínio {domain_name}",
        "domainType": "Source-aligned",
        "parent": domain_name
    })
    print(f"  {GREEN}✔ Domínio: {domain_name} | Subdomínio: {full_domain_fqn}{RESET}")

    print(f"\n{BOLD}{CYAN}>>> [Etapa 2] Registrando Time Proprietário (Squad)...{RESET}")
    team_resp = client.put("v1/teams", {
        "name": team_name,
        "displayName": team_display,
        "description": f"Time proprietário e responsável pelo produto {dp_name} (Email: {team_email})",
        "teamType": "Group"
    })
    team_id = team_resp["id"]
    print(f"  {GREEN}✔ Team: {team_display} ({team_name}) - ID: {team_id}{RESET}")

    # 3. Registrar Serviços e Schemas
    print(f"\n{BOLD}{CYAN}>>> [Etapa 3] Registrando Serviços e Schemas de Armazenamento...{RESET}")
    
    # 3.1 DuckDB Server (CustomDatabase com ícone DuckDB)
    # Se o serviço existir com serviceType incompatível (ex: Postgres), deleta para recriar
    existing_duckdb = client.get("v1/services/databaseServices/name/duckdb_server")
    if existing_duckdb.get("id") and existing_duckdb.get("serviceType") != "CustomDatabase":
        print(f"  {YELLOW}⟳ Migrando duckdb_server de {existing_duckdb.get('serviceType')} → CustomDatabase...{RESET}")
        client.delete(f"v1/services/databaseServices/{existing_duckdb['id']}?recursive=true&hardDelete=true")
    client.put("v1/services/databaseServices", {
        "name": "duckdb_server",
        "displayName": "DuckDB Server",
        "serviceType": "CustomDatabase",
        "description": "DuckDB Server Analítico no cluster K3s (pg_duckdb)",
        "style": {
            "iconURL": "https://duckdb.org/images/favicon/apple-touch-icon.png",
            "color": "#FFF100"
        },
        "connection": {
            "config": {
                "type": "CustomDatabase",
                "sourcePythonClass": "metadata.ingestion.source.database.customdatabase.metadata.CustomDatabaseSource"
            }
        }
    })
    client.put("v1/databases", {
        "name": "investments",
        "service": "duckdb_server",
        "description": "Catálogo Analítico DuckDB de Investimentos"
    })

    # Criar Schemas no DuckDB Server se existirem portas de saída analíticas
    created_schemas = set()
    output_ports = odps.get("outputPorts", [])
    for port in output_ports:
        fqn = port.get("fullyQualifiedName", "")
        platform = port.get("platform", "")
        if "duckdb" in platform or "iceberg" in platform or fqn.startswith("investments."):
            parts = fqn.split(".")
            if len(parts) >= 3:
                schema_name = parts[1]
                if schema_name not in created_schemas:
                    client.put("v1/databaseSchemas", {
                        "name": schema_name,
                        "database": "duckdb_server.investments",
                        "description": f"Schema analítico {schema_name} no DuckDB Server",
                        "domains": [full_domain_fqn]
                    })
                    created_schemas.add(schema_name)
                    print(f"  {GREEN}✔ DuckDB Schema: duckdb_server.investments.{schema_name}{RESET}")

    # 3.2 MongoDB Serving Layer (se aplicável)
    has_mongo = any("mongo" in p.get("platform", "") or "mongo" in p.get("type", "") for p in output_ports)
    if has_mongo:
        client.put("v1/services/databaseServices", {
            "name": "mongodb_k3s",
            "displayName": "MongoDB Serving Layer",
            "serviceType": "MongoDB",
            "description": "Cluster Operacional MongoDB local no K3s para Serving Layer de Canais Digitais",
            "connection": {
                "config": {
                    "type": "MongoDB",
                    "hostPort": "mongodb.openmetadata.svc.cluster.local:27017"
                }
            }
        })
        client.put("v1/databases", {
            "name": "investments_serving",
            "service": "mongodb_k3s",
            "description": "Database Operacional MongoDB para Servir Posições e Extratos"
        })
        client.put("v1/databaseSchemas", {
            "name": "collections",
            "database": "mongodb_k3s.investments_serving",
            "description": "Coleções operacionais ativas",
            "domains": [full_domain_fqn]
        })
        print(f"  {GREEN}✔ MongoDB Service & Database: mongodb_k3s.investments_serving.collections{RESET}")

    # 3.3 Sistemas de Origem (para Source-Aligned)
    input_ports = odps.get("inputPorts", [])
    source_tables = []
    for inp in input_ports:
        stype = inp.get("type", "")
        src_system = inp.get("sourceSystem", "")
        tech = (inp.get("technology") or "").lower()
        src_lower = src_system.lower()

        if stype in ("database-cdc", "rest-api") and src_system:
            sys_id = sanitize_name(src_lower)

            if "oracle" in src_lower or "oracle" in tech:
                svc_type = "Oracle"
                conn_config = {
                    "type": "Oracle",
                    "hostPort": f"{sys_id}.corp.local:1521"
                }
            elif "db2" in src_lower or "db2" in tech or "ibm" in tech:
                svc_type = "Db2"
                conn_config = {
                    "type": "Db2",
                    "hostPort": f"{sys_id}.corp.local:50000",
                    "database": "CORE_PROD"
                }
            else:
                svc_type = "Postgres"
                conn_config = {
                    "type": svc_type,
                    "hostPort": f"{sys_id}.corp.local:5432",
                    "database": "CORE_PROD"
                }

            # Se o serviço existir com serviceType incompatível, deleta para recriar
            existing_svc = client.get(f"v1/services/databaseServices/name/{sys_id}")
            if existing_svc.get("id") and existing_svc.get("serviceType") != svc_type:
                client.delete(f"v1/services/databaseServices/{existing_svc['id']}?recursive=true&hardDelete=true")

            client.put("v1/services/databaseServices", {
                "name": sys_id,
                "displayName": src_system,
                "serviceType": svc_type,
                "description": f"Sistema de Origem Transacional: {src_system} ({inp.get('name')})",
                "connection": {
                    "config": conn_config
                }
            })
            client.put("v1/databases", {
                "name": "CORE_PROD",
                "service": sys_id,
                "description": f"Database transacional do sistema {src_system}"
            })
            client.put("v1/databaseSchemas", {
                "name": "raw",
                "database": f"{sys_id}.CORE_PROD",
                "description": "Schema de extração raw de dados"
            })
            # Tabela de origem
            src_table_name = f"tb_{sys_id}_inbound"
            src_tbl_payload = {
                "name": src_table_name,
                "databaseSchema": f"{sys_id}.CORE_PROD.raw",
                "description": f"Origem bruta capturada de {src_system}: {inp.get('description', '')}",
                "tableType": "Regular",
                "columns": [
                    {"name": "raw_payload", "dataType": "VARCHAR", "dataLength": 2048, "description": "Carga raw capturada"},
                    {"name": "_cdc_timestamp", "dataType": "TIMESTAMP", "description": "Carimbo de data/hora do evento"}
                ]
            }
            src_tbl = client.put("v1/tables", src_tbl_payload)
            source_tables.append((f"{sys_id}.CORE_PROD.raw.{src_table_name}", src_tbl["id"]))
            print(f"  {GREEN}✔ Sistema de Origem: {sys_id}.CORE_PROD.raw.{src_table_name}{RESET}")

    # 3.1 Provisionar Glossário Corporativo e Termos de Governança
    provision_glossary_and_terms(client, repo_path)

    # 4. Parse dos Contratos ODCS e Registro de Tabelas
    print(f"\n{BOLD}{CYAN}>>> [Etapa 4] Fazendo Parse dos Contratos ODCS e Registrando Tabelas...{RESET}")
    published_assets = []
    table_fqn_to_id = {}

    # Mapear cada outputPort ao seu contrato ODCS
    for port in output_ports:
        port_id = port.get("id")
        port_name = port.get("name")
        port_fqn = port.get("fullyQualifiedName", "")
        contract_rel_path = port.get("contract")

        if not contract_rel_path:
            continue

        contract_file = repo_path / contract_rel_path
        if not contract_file.exists():
            print(f"  {YELLOW}Aviso: Contrato {contract_file} não encontrado.{RESET}")
            continue

        with open(contract_file, "r", encoding="utf-8") as f:
            odcs = yaml.safe_load(f)

        odcs_models = odcs.get("models", [])
        for model in odcs_models:
            model_table_raw = model.get("table", "")
            # Determinar se a tabela pertence a DuckDB ou MongoDB
            if "mongodb" in port.get("platform", "") or "document" in port.get("type", ""):
                db_schema_fqn = "mongodb_k3s.investments_serving.collections"
                table_name = model_table_raw.split(".")[-1]
            else:
                parts = model_table_raw.split(".")
                if len(parts) >= 3:
                    schema_name = parts[1]
                    table_name = parts[2]
                else:
                    schema_name = "silver"
                    table_name = parts[-1]
                db_schema_fqn = f"duckdb_server.investments.{schema_name}"

            # Identificar chaves primárias
            pk_cols = [c.get("name") for c in model.get("columns", []) if c.get("primaryKey")]

            # Construir as colunas com tipagem, tags PII e termos de Glossário
            columns = []
            for col in model.get("columns", []):
                col_name = col.get("name")
                c_type = map_odcs_type_to_om(col.get("logicalType", ""), col.get("physicalType", ""))
                col_payload = {
                    "name": col_name,
                    "dataType": c_type,
                    "description": col.get("description", "")
                }
                if c_type == "VARCHAR":
                    col_payload["dataLength"] = col.get("dataLength", 255)
                # Se for PK simples, anexa no campo da coluna
                if col.get("primaryKey") and len(pk_cols) == 1:
                    col_payload["constraint"] = "PRIMARY_KEY"

                col_tags = []
                # Tags de governança e PII
                if col.get("classification") == "PII":
                    col_tags.append({
                        "tagFQN": "PersonalData.Personal",
                        "labelType": "Manual",
                        "state": "Confirmed"
                    })
                # Termo de glossário corporativo
                bg_term = col.get("businessGlossaryTerm")
                if bg_term:
                    term_name = bg_term.split(".")[-1]
                    col_tags.append({
                        "tagFQN": f"Investimentos.{term_name}",
                        "source": "Glossary",
                        "labelType": "Manual",
                        "state": "Confirmed"
                    })
                if col_tags:
                    col_payload["tags"] = col_tags

                columns.append(col_payload)

            layer_tier, cert_tag = get_layer_and_cert(table_name)
            retention_iso = extract_iso_retention(odcs, odps)

            table_tags = [{
                "tagFQN": layer_tier,
                "labelType": "Manual",
                "state": "Confirmed"
            }]

            table_payload = {
                "name": table_name,
                "databaseSchema": db_schema_fqn,
                "description": f"[{odcs.get('info', {}).get('title', 'Contrato ODCS')}] {model.get('description', '')}",
                "tableType": "Regular",
                "domains": [full_domain_fqn],
                "owners": [{"id": team_id, "type": "team"}],
                "tags": table_tags,
                "retentionPeriod": retention_iso,
                "columns": columns
            }

            # Se for PK composta, anexa em tableConstraints
            if len(pk_cols) > 1:
                table_payload["tableConstraints"] = [{
                    "constraintType": "PRIMARY_KEY",
                    "columns": pk_cols
                }]

            tbl_resp = client.put("v1/tables", table_payload)
            tbl_id = tbl_resp["id"]
            final_tbl_fqn = f"{db_schema_fqn}.{table_name}"
            table_fqn_to_id[final_tbl_fqn] = tbl_id
            table_fqn_to_id[model_table_raw] = tbl_id
            table_fqn_to_id[port_fqn] = tbl_id

            # Aplicar Certificação e Status Draft na Tabela
            now_ms = int(time.time() * 1000)
            try:
                client.patch(f"v1/tables/{tbl_id}", [
                    {"op": "add", "path": "/entityStatus", "value": "Draft"},
                    {"op": "add", "path": "/certification", "value": {
                        "tagLabel": {
                            "tagFQN": cert_tag,
                            "labelType": "Automated",
                            "state": "Confirmed"
                        },
                        "appliedDate": now_ms
                    }}
                ])
            except Exception as e:
                print(f"  {YELLOW}Aviso ao aplicar certificação/status: {e}{RESET}")

            # Upload de Amostra de Dados (Sample Data)
            sample_columns = [c["name"] for c in columns]
            sample_rows = []

            # Procurar arquivo seed correspondente
            seed_file = None
            seeds_dir = repo_path / "seeds"
            if seeds_dir.exists():
                for f in seeds_dir.glob("*.csv"):
                    base_simple = table_name.replace("silver_", "").replace("gold_", "")
                    if table_name in f.name or base_simple in f.name:
                        seed_file = f
                        break

            csv_rows_dict = []
            if seed_file and seed_file.exists():
                with open(seed_file, "r", encoding="utf-8") as sf:
                    reader = csv.DictReader(sf)
                    for r in reader:
                        if any(r.values()):
                            csv_rows_dict.append(r)
                        if len(csv_rows_dict) >= 10:
                            break

            num_rows = max(len(csv_rows_dict), 5)
            for r_idx in range(num_rows):
                row_val = []
                csv_item = csv_rows_dict[r_idx] if r_idx < len(csv_rows_dict) else {}
                for col in columns:
                    c_name = col["name"]
                    c_type = col["dataType"]
                    val = None
                    if csv_item:
                        if c_name in csv_item:
                            val = csv_item[c_name]
                        else:
                            for k, v in csv_item.items():
                                if k.replace("_retido", "") == c_name.replace("_retido", "") or k in c_name or c_name in k:
                                    val = v
                                    break
                    if val is None or val == "":
                        if c_type in ("INT", "BIGINT"):
                            val = str(1000 * (r_idx + 1))
                        elif c_type in ("NUMERIC", "DOUBLE"):
                            val = f"{5000.0 * (r_idx + 1):.2f}"
                        elif c_type == "DATE":
                            val = f"2026-09-{10 + (r_idx + 1):02d}"
                        elif c_type == "TIMESTAMP":
                            val = f"2026-09-{10 + (r_idx + 1):02d} 12:00:00"
                        elif c_type == "BOOLEAN":
                            val = "true"
                        elif "id" in c_name.lower() or "cd" in c_name.lower():
                            val = f"{c_name.upper()}_{r_idx + 1:03d}"
                        else:
                            val = f"SAMPLE_{c_name.upper()}"
                    row_val.append(str(val))
                sample_rows.append(row_val)

            if sample_columns and sample_rows:
                try:
                    client.put(f"v1/tables/{tbl_id}/sampleData", {
                        "columns": sample_columns,
                        "rows": sample_rows
                    })
                    print(f"  {GREEN}✔ Amostra de Dados (Sample Data):{RESET} {len(sample_rows)} linhas carregadas.")
                except Exception as e:
                    print(f"  {YELLOW}Aviso ao enviar amostra de dados: {e}{RESET}")

            published_assets.append({"id": tbl_id, "type": "table"})
            print(f"  {GREEN}✔ Tabela Registrada (Draft):{RESET} {BOLD}{final_tbl_fqn}{RESET} | Camada: {layer_tier} | Cert: {cert_tag} | Retenção: {retention_iso}")

            # Importar e Vincular Contrato ODCS nativo na Tabela (Draft)
            try:
                odcs_yaml_str = build_om_odcs_yaml(odcs, table_name, final_tbl_fqn, dp_name, domain_name, status="draft")
                client.put_yaml(f"v1/dataContracts/odcs/yaml?entityId={tbl_id}&entityType=table&mode=merge", odcs_yaml_str)
                tbl_detail = client.get(f"v1/tables/{tbl_id}?fields=dataContract")
                contract_id = tbl_detail.get("dataContract", {}).get("id")
                if contract_id:
                    client.patch(f"v1/dataContracts/{contract_id}", [
                        {"op": "add", "path": "/entityStatus", "value": "Draft"}
                    ])
                print(f"  {GREEN}✔ Contrato ODCS Vinculado (Draft):{RESET} {odcs.get('id')} ({odcs.get('info', {}).get('title')})")
            except Exception as e:
                print(f"  {YELLOW}Aviso ao importar contrato ODCS: {e}{RESET}")

            # Patch para garantir a vinculação dos termos de glossário e tags PII nas colunas após o merge do contrato
            try:
                tbl_detail = client.get(f"v1/tables/{tbl_id}?fields=columns")
                patch_ops = []
                for idx, c in enumerate(tbl_detail.get("columns", [])):
                    c_name = c.get("name")
                    # Encontrar a coluna correspondente no contrato ODCS
                    matched_odcs_col = None
                    for odcs_col in model.get("columns", []):
                        if odcs_col.get("name") == c_name:
                            matched_odcs_col = odcs_col
                            break
                    if not matched_odcs_col:
                        continue
                    has_glossary = matched_odcs_col.get("businessGlossaryTerm")
                    has_pii = matched_odcs_col.get("classification") == "PII"
                    if not has_glossary and not has_pii:
                        continue
                    # Reconstruir a lista de tags esperada para esta coluna
                    existing_tags = c.get("tags", [])
                    existing_fqns = {tg.get("tagFQN") for tg in existing_tags}
                    new_tags = list(existing_tags)
                    if has_pii and "PersonalData.Personal" not in existing_fqns:
                        new_tags.append({
                            "tagFQN": "PersonalData.Personal",
                            "labelType": "Manual",
                            "state": "Confirmed"
                        })
                    if has_glossary:
                        t_name = has_glossary.split(".")[-1]
                        tag_fqn = f"Investimentos.{t_name}"
                        if tag_fqn not in existing_fqns:
                            new_tags.append({
                                "tagFQN": tag_fqn,
                                "source": "Glossary",
                                "labelType": "Manual",
                                "state": "Confirmed"
                            })
                    if len(new_tags) > len(existing_tags):
                        patch_ops.append({
                            "op": "replace",
                            "path": f"/columns/{idx}/tags",
                            "value": new_tags
                        })
                if patch_ops:
                    client.patch(f"v1/tables/{tbl_id}", patch_ops)
            except Exception as pe:
                print(f"  {YELLOW}Aviso patch termos: {pe}{RESET}")

            # Registrar TestCases de Qualidade ODCS na Observabilidade do OpenMetadata
            entity_link = f"<#E::table::{final_tbl_fqn}>"
            registered_tests = 0
            for q in odcs.get("quality", []):
                q_name = q.get("name")
                rule_val = q.get("rule", "")
                if not rule_val and "maxAgeHours" in q:
                    rule_val = f"maxAgeHours <= {q['maxAgeHours']}"
                if q_name:
                    try:
                        client.put("v1/dataQuality/testCases", {
                            "name": q_name,
                            "displayName": q.get("description", q_name).strip()[:128] or q_name,
                            "description": q.get("description", f"Regra ODCS: {rule_val}"),
                            "entityLink": entity_link,
                            "testDefinition": "tableCustomSQLQuery",
                            "parameterValues": [
                                {"name": "sqlExpression", "value": rule_val or "1=1"}
                            ]
                        })
                        registered_tests += 1
                    except Exception as e:
                        print(f"  {YELLOW}Aviso ao registrar teste {q_name}: {e}{RESET}")
            if registered_tests > 0:
                print(f"  {GREEN}✔ Observabilidade (Data Quality):{RESET} {registered_tests} testes ODCS vinculados à tabela.")

    # 5. Registro do Data Product no Marketplace
    print(f"\n{BOLD}{CYAN}>>> [Etapa 5] Publicando Data Product no Marketplace OpenMetadata via ODPS v4.1...{RESET}")
    # Definir tipo de Data Product conforme enum do OpenMetadata
    is_derived = "derivado" in str(repo_path) or "consolidado" in dp_name.lower()
    dp_type = "DERIVED_DATA" if is_derived else "RAW_DATA"

    # Tenta publicar primeiro via endpoint nativo ODPS v4.1 YAML
    with open(odps_file, "r", encoding="utf-8") as f:
        odps_raw_yaml = f.read()

    dp_created_id = None
    try:
        dp_resp = client.put_yaml(f"v1/dataProducts/odps/yaml?domain={full_domain_fqn}&strategy=merge", odps_raw_yaml)
        dp_created_id = dp_resp.get("id")
        print(f"  {GREEN}✔ Data Product Publicado via ODPS v4.1:{RESET} {BOLD}{dp_name}{RESET} (ID: {dp_created_id}, Domínio: {full_domain_fqn})")
    except Exception as e:
        print(f"  {YELLOW}Aviso ao importar ODPS v4.1 YAML ({e}), aplicando via /v1/dataProducts...{RESET}")

    if not dp_created_id:
        dp_payload = {
            "name": dp_name,
            "displayName": dp_name,
            "description": f"{dp_desc}\n\n**Subdomínio:** {subdomain_raw} | **Versão:** {dp_version} | **Squad:** {team_display}",
            "domains": [full_domain_fqn],
            "owners": [{"id": team_id, "type": "team"}],
            "visibility": "PUBLIC",
            "dataProductType": dp_type
        }
        dp_resp = client.put("v1/dataProducts", dp_payload)
        dp_created_id = dp_resp["id"]
        print(f"  {GREEN}✔ Data Product Publicado:{RESET} {BOLD}{dp_name}{RESET} (ID: {dp_created_id}, Domínio: {full_domain_fqn}, Visibilidade: PUBLIC)")

    if dp_created_id:
        try:
            client.patch(f"v1/dataProducts/{dp_created_id}", [
                {"op": "add", "path": "/entityStatus", "value": "Draft"},
                {"op": "add", "path": "/lifecycleStage", "value": "DEVELOPMENT"},
                {"op": "add", "path": "/owners", "value": [{"id": team_id, "type": "team"}]}
            ])
            print(f"  {GREEN}✔ Status Inicial:{RESET} Data Product em {BOLD}Draft{RESET} (Fase: {BOLD}DEVELOPMENT{RESET}) com Owner {team_display}.")
        except Exception as e:
            print(f"  {YELLOW}Aviso ao atualizar status Draft do Data Product: {e}{RESET}")

    # 5.1 Vincular assets oficialmente via endpoint /assets/add
    if published_assets:
        assets_payload = {
            "assets": published_assets,
            "dryRun": False
        }
        client.put(f"v1/dataProducts/{dp_name}/assets/add", assets_payload)
        print(f"  {GREEN}✔ Assets Vinculados:{RESET} {len(published_assets)} tabelas associadas com sucesso via API assets/add.")

    # 5.2 Vincular Portas de Saída via endpoint /outputPorts/add
    if published_assets:
        client.put(f"v1/dataProducts/{dp_name}/outputPorts/add", {"assets": published_assets, "dryRun": False})
        print(f"  {GREEN}✔ Portas de Saída (Output Ports):{RESET} {len(published_assets)} portas associadas via API outputPorts/add.")

    # 5.3 Vincular Portas de Entrada via endpoint /inputPorts/add
    input_assets = []
    for _, src_id in source_tables:
        input_assets.append({"id": src_id, "type": "table"})
    for inp in input_ports:
        upstream_fqn = inp.get("fullyQualifiedName")
        if upstream_fqn:
            parts = upstream_fqn.split(".")
            om_upstream_fqn = f"duckdb_server.investments.{parts[1]}.{parts[2]}" if len(parts) >= 3 else f"duckdb_server.investments.{upstream_fqn}"
            up_tbl = client.get(f"v1/tables/name/{om_upstream_fqn}")
            if up_tbl.get("id"):
                input_assets.append({"id": up_tbl["id"], "type": "table"})

    if input_assets:
        client.put(f"v1/dataProducts/{dp_name}/inputPorts/add", {"assets": input_assets, "dryRun": False})
        print(f"  {GREEN}✔ Portas de Entrada (Input Ports):{RESET} {len(input_assets)} portas associadas via API inputPorts/add.")

    # 6. Grafo de Linhagem e Resolução Automática de Dependências
    print(f"\n{BOLD}{CYAN}>>> [Etapa 6] Conectando Grafo de Linhagem & Dependências Upstream...{RESET}")

    def add_lineage(from_id, to_id, from_desc, to_desc):
        try:
            lineage_payload = {
                "edge": {
                    "fromEntity": {"id": from_id, "type": "table"},
                    "toEntity": {"id": to_id, "type": "table"}
                }
            }
            client.put("v1/lineage", lineage_payload)
            print(f"  🔗 Linhagem: {BOLD}{from_desc}{RESET} ➔ {BOLD}{to_desc}{RESET}")
        except Exception as e:
            print(f"  {YELLOW}Aviso ao registrar linhagem ({from_desc} ➔ {to_desc}): {e}{RESET}")

    # Se tiver origens transacionais capturadas (Source-Aligned)
    for src_name, src_id in source_tables:
        for asset in published_assets:
            add_lineage(src_id, asset["id"], src_name, f"asset:{asset['id']}")

    # Se tiver inputPorts declaradas de outros produtos (Consumer-Aligned)
    for inp in input_ports:
        upstream_dp = inp.get("upstreamDataProduct")
        upstream_fqn = inp.get("fullyQualifiedName")
        if upstream_dp and upstream_fqn:
            # Buscar ID da tabela upstream no OpenMetadata
            # O nome no DuckDB Server é duckdb_server.investments.<schema>.<table>
            parts = upstream_fqn.split(".")
            if len(parts) >= 3:
                om_upstream_fqn = f"duckdb_server.investments.{parts[1]}.{parts[2]}"
            else:
                om_upstream_fqn = f"duckdb_server.investments.{upstream_fqn}"

            up_table_obj = client.get(f"v1/tables/name/{om_upstream_fqn}")
            up_table_id = up_table_obj.get("id")

            if up_table_id:
                # Conectar à primeira tabela Silver do produto derivado
                # que corresponda ao fluxo
                for port in output_ports:
                    dest_fqn = port.get("fullyQualifiedName", "")
                    if "silver" in dest_fqn:
                        dest_id = table_fqn_to_id.get(dest_fqn)
                        if dest_id:
                            add_lineage(up_table_id, dest_id, om_upstream_fqn, dest_fqn)
            else:
                print(f"  {YELLOW}Aviso Upstream:{RESET} Tabela {om_upstream_fqn} do produto {upstream_dp} ainda não encontrada no OpenMetadata (faça o deploy dela antes).")

    # Se for o produto derivado, conectar Silver -> Gold e Silver -> MongoDB
    if "derivado" in str(repo_path) or "consolidado" in dp_name.lower():
        silver_pos = table_fqn_to_id.get("investments.renda_fixa.silver_posicao") or table_fqn_to_id.get("duckdb_server.investments.renda_fixa.silver_posicao")
        silver_mov = table_fqn_to_id.get("investments.renda_fixa.silver_movimentacao") or table_fqn_to_id.get("duckdb_server.investments.renda_fixa.silver_movimentacao")
        gold_pos = table_fqn_to_id.get("investments.renda_fixa.gold_saldo_investido") or table_fqn_to_id.get("duckdb_server.investments.renda_fixa.gold_saldo_investido")
        gold_mov = table_fqn_to_id.get("investments.renda_fixa.gold_movimentacao_sumarizada") or table_fqn_to_id.get("duckdb_server.investments.renda_fixa.gold_movimentacao_sumarizada")
        mongo_out = table_fqn_to_id.get("mongodb_k3s.investments_serving.collections.rf_customer_positions")

        if silver_pos and gold_pos:
            add_lineage(silver_pos, gold_pos, "silver_posicao", "gold_saldo_investido")
        if silver_mov and gold_mov:
            add_lineage(silver_mov, gold_mov, "silver_movimentacao", "gold_movimentacao_sumarizada")
        if silver_pos and mongo_out:
            add_lineage(silver_pos, mongo_out, "silver_posicao", "mongodb.rf_customer_positions")

    # 7. Resumo com Links Clicáveis
    print(f"\n{BOLD}{GREEN}{'='*80}{RESET}")
    print(f"{BOLD}{GREEN}   DEPLOY DO PRODUTO [{dp_name}] CONCLUÍDO COM SUCESSO!                     {RESET}")
    print(f"{BOLD}{GREEN}{'='*80}{RESET}")
    print(f"\n{BOLD}Painéis de Consulta no OpenMetadata:{RESET}")
    print(f"  • {BOLD}{CYAN}Marketplace Global (Explore):{RESET}   {YELLOW}{client.base_url}/explore/dataProducts{RESET}")
    print(f"  • {BOLD}{CYAN}Domínio & Subdomínio:{RESET}          {YELLOW}{client.base_url}/domain/{full_domain_fqn}{RESET}")
    print(f"  • {BOLD}{CYAN}Data Product [{dp_name}]:{RESET}          {YELLOW}{client.base_url}/domain/{full_domain_fqn}/dataProducts/{dp_name}{RESET}")
    
    first_asset_fqn = None
    for k, v in table_fqn_to_id.items():
        if k.startswith("duckdb_server") or k.startswith("mongodb_k3s"):
            first_asset_fqn = k
            break
    if not first_asset_fqn and table_fqn_to_id:
        first_asset_fqn = list(table_fqn_to_id.keys())[0]

    if first_asset_fqn:
        print(f"  • {BOLD}{CYAN}Tabela & Contrato ODCS:{RESET}          {YELLOW}{client.base_url}/table/{first_asset_fqn}{RESET}")
        print(f"  • {BOLD}{CYAN}Grafo de Linhagem:{RESET}               {YELLOW}{client.base_url}/table/{first_asset_fqn}/lineage{RESET}\n")


def resolve_om_url(explicit_url: str = None) -> str:
    if explicit_url:
        return explicit_url
    env_url = os.getenv("OPENMETADATA_SERVER_URL")
    if env_url:
        return env_url
    for candidate in [
        "http://localhost",
        "http://localhost:8585",
        "http://openmetadata.openmetadata.svc.cluster.local:8585",
    ]:
        try:
            r = requests.get(f"{candidate}/api/v1/system/version", timeout=1.5)
            if r.status_code == 200:
                return candidate
        except Exception:
            pass
    return "http://localhost"


def main():
    parser = argparse.ArgumentParser(description="Deploy de Data Product no OpenMetadata via ODPS/ODCS")
    parser.add_argument("repo_path", help="Caminho relativo ou absoluto do repositório (ex: repos/sist-cdb)")
    parser.add_argument("--url", default=None, help="URL base do OpenMetadata (default: auto-detect)")
    parser.add_argument("--email", default=os.getenv("OPENMETADATA_ADMIN_EMAIL", "admin@open-metadata.org"), help="Email do Admin")
    parser.add_argument("--password", default=os.getenv("OPENMETADATA_ADMIN_PASSWORD", "admin"), help="Senha do Admin")
    args = parser.parse_args()

    om_url = resolve_om_url(args.url)
    client = OpenMetadataClient(om_url, args.email, args.password)
    deploy_repository_product(args.repo_path, client)


if __name__ == "__main__":
    main()
