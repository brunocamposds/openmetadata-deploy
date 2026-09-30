#!/usr/bin/env python3
"""
==============================================================================
OpenMetadata CI/CD Pipeline - Data Product Approval Engine
==============================================================================
Simula a etapa de aprovação / promoção para Produção na esteira CI/CD:
- Ativa o status do Data Product para 'Approved' e ciclo de vida para 'PRODUCTION'
- Ativa o status das Tabelas (Assets/Output Ports) para 'Approved'
- Ativa o status dos Contratos ODCS para 'Approved' e status='active'
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

    def get(self, endpoint: str) -> dict:
        url = f"{self.api_url}/{endpoint}"
        resp = requests.get(url, headers=self.headers, timeout=120)
        if resp.status_code == 200:
            return resp.json()
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


def build_om_odcs_yaml(odcs_data: dict, table_name: str, full_table_fqn: str, dp_name: str, domain_name: str, status: str = "active") -> str:
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


def approve_repository_product(repo_path_str: str, client: OpenMetadataClient):
    repo_path = Path(repo_path_str).resolve()
    odps_file = repo_path / "data-product.odps.yaml"

    if not odps_file.exists():
        raise FileNotFoundError(f"Arquivo ODPS não encontrado em: {odps_file}")

    with open(odps_file, "r", encoding="utf-8") as f:
        odps = yaml.safe_load(f)

    product_details = odps.get("product", {}).get("details", {}).get("en", {})
    dp_name = odps.get("name") or product_details.get("name")
    domain_name = odps.get("domain", "Investimentos")
    subdomain_raw = odps.get("subDomain", "Geral")
    subdomain_name = sanitize_name(subdomain_raw)
    full_domain_fqn = f"{domain_name}.{subdomain_name}"

    print(f"\n{BOLD}{GREEN}{'='*80}{RESET}")
    print(f"{BOLD}{GREEN}   OpenMetadata CI/CD Pipeline - Data Product Approval Engine              {RESET}")
    print(f"{BOLD}{GREEN}   Promoção para Produção & Aprovação de Contratos ODCS / ODPS              {RESET}")
    print(f"{BOLD}{GREEN}{'='*80}{RESET}")
    print(f"{BLUE}Repositório:{RESET} {BOLD}{repo_path}{RESET}")
    print(f"{BLUE}Produto de Dados:{RESET} {BOLD}{dp_name}{RESET} (Domínio: {full_domain_fqn})")

    # 1. Obter Data Product
    dp_obj = client.get(f"v1/dataProducts/name/{dp_name}")
    if not dp_obj.get("id"):
        all_dps = client.get("v1/dataProducts")
        for d in all_dps.get("data", []):
            if d.get("name") == dp_name or d.get("fullyQualifiedName") == dp_name:
                dp_obj = d
                break

    if not dp_obj.get("id"):
        raise RuntimeError(f"Produto de dados {dp_name} não encontrado no OpenMetadata. Execute o deploy primeiro!")

    dp_id = dp_obj["id"]

    # 2. Aprovar Data Product (Approved + PRODUCTION)
    print(f"\n{BOLD}{CYAN}>>> [Etapa 1] Promovendo Data Product [{dp_name}] para PRODUÇÃO...{RESET}")
    patch_dp = [
        {"op": "add", "path": "/entityStatus", "value": "Approved"},
        {"op": "add", "path": "/lifecycleStage", "value": "PRODUCTION"}
    ]
    client.patch(f"v1/dataProducts/{dp_id}", patch_dp)
    print(f"  {GREEN}✔ Data Product Aprovado:{RESET} Status: {BOLD}Approved{RESET} | Fase: {BOLD}PRODUCTION{RESET}")

    # 3. Aprovar Tabelas e Contratos ODCS
    print(f"\n{BOLD}{CYAN}>>> [Etapa 2] Aprovando Tabelas e Ativando Contratos ODCS...{RESET}")
    
    # Coletar portas de saída e seus arquivos ODCS
    output_ports = odps.get("outputPorts", [])
    contract_map = {}
    for port in output_ports:
        fqn = port.get("fullyQualifiedName")
        rel_c = port.get("contract")
        if fqn and rel_c:
            contract_map[fqn] = rel_c

    # Buscar assets vinculados via /assets
    assets_resp = client.get(f"v1/dataProducts/{dp_id}/assets")
    assets = assets_resp.get("data", []) or []

    # Se ainda estiver vazio, tentar buscar diretamente as tabelas do outputPorts do manifesto
    if not assets:
        for port in output_ports:
            fqn = port.get("fullyQualifiedName", "")
            parts = fqn.split(".")
            if len(parts) >= 3:
                om_tbl_fqn = f"duckdb_server.investments.{parts[1]}.{parts[2]}"
            else:
                om_tbl_fqn = f"duckdb_server.investments.{fqn}"
            t_data = client.get(f"v1/tables/name/{om_tbl_fqn}")
            if t_data.get("id"):
                assets.append({"id": t_data["id"], "type": "table", "fullyQualifiedName": om_tbl_fqn})

    approved_tables = 0
    approved_contracts = 0

    for asset in assets:
        tbl_id = asset.get("id")
        if not tbl_id:
            continue

        tbl_data = client.get(f"v1/tables/{tbl_id}?fields=dataContract")
        tbl_fqn = tbl_data.get("fullyQualifiedName", asset.get("fullyQualifiedName", tbl_id))
        tbl_name = tbl_data.get("name", "")

        # 3.1 Aprovar Tabela
        try:
            client.patch(f"v1/tables/{tbl_id}", [
                {"op": "add", "path": "/entityStatus", "value": "Approved"}
            ])
            approved_tables += 1
            print(f"  {GREEN}✔ Tabela Aprovada:{RESET} {BOLD}{tbl_fqn}{RESET} (Status: Approved)")
        except Exception as e:
            print(f"  {YELLOW}Aviso ao aprovar tabela {tbl_fqn}: {e}{RESET}")

        # 3.2 Aprovar Contrato ODCS
        contract = tbl_data.get("dataContract")
        if contract and contract.get("id"):
            try:
                client.patch(f"v1/dataContracts/{contract['id']}", [
                    {"op": "add", "path": "/entityStatus", "value": "Approved"}
                ])
                approved_contracts += 1
                print(f"  {GREEN}✔ Contrato ODCS Aprovado:{RESET} ID: {contract['id']} (Status: Approved)")
            except Exception as e:
                print(f"  {YELLOW}Aviso ao aprovar contrato da tabela {tbl_fqn}: {e}{RESET}")

        # 3.3 Re-sincronizar YAML do ODCS com status 'active'
        for port_fqn, rel_path in contract_map.items():
            if tbl_name in port_fqn or port_fqn in tbl_fqn:
                c_file = repo_path / rel_path
                if c_file.exists():
                    try:
                        with open(c_file, "r", encoding="utf-8") as cf:
                            c_raw = yaml.safe_load(cf)
                        active_yaml = build_om_odcs_yaml(c_raw, tbl_name, tbl_fqn, dp_name, domain_name, status="active")
                        client.put_yaml(f"v1/dataContracts/odcs/yaml?entityId={tbl_id}&entityType=table&mode=merge", active_yaml)
                        print(f"  {GREEN}✔ Contrato ODCS Promovido a Ativo (active):{RESET} {c_file.name}")
                    except Exception as e:
                        print(f"  {YELLOW}Aviso ao promover ODCS YAML: {e}{RESET}")

    # 4. Resumo com Links
    print(f"\n{BOLD}{GREEN}{'='*80}{RESET}")
    print(f"{BOLD}{GREEN}   PRODUTO DE DADOS [{dp_name}] APROVADO E ATIVADO COM SUCESSO!            {RESET}")
    print(f"{BOLD}{GREEN}{'='*80}{RESET}")
    print(f"  • {BOLD}Status do Produto:{RESET} {GREEN}Approved (PRODUCTION){RESET}")
    print(f"  • {BOLD}Tabelas Aprovadas:{RESET} {GREEN}{approved_tables}{RESET}")
    print(f"  • {BOLD}Contratos Ativados:{RESET} {GREEN}{approved_contracts}{RESET}")
    print(f"\n{BOLD}Painéis no OpenMetadata:{RESET}")
    print(f"  • {BOLD}{CYAN}Data Product no Marketplace:{RESET}  {YELLOW}{client.base_url}/domain/{full_domain_fqn}/dataProducts/{dp_name}{RESET}")
    print(f"  • {BOLD}{CYAN}Marketplace Geral:{RESET}            {YELLOW}{client.base_url}/explore/dataProducts{RESET}\n")


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
    parser = argparse.ArgumentParser(description="Aprovação de Data Product e Contratos ODCS no OpenMetadata")
    parser.add_argument("repo_path", help="Caminho relativo ou absoluto do repositório (ex: repos/sist-cdb)")
    parser.add_argument("--url", default=None, help="URL base do OpenMetadata (default: auto-detect)")
    parser.add_argument("--email", default=os.getenv("OPENMETADATA_ADMIN_EMAIL", "admin@open-metadata.org"), help="Email do Admin")
    parser.add_argument("--password", default=os.getenv("OPENMETADATA_ADMIN_PASSWORD", "admin"), help="Senha do Admin")
    args = parser.parse_args()

    om_url = resolve_om_url(args.url)
    client = OpenMetadataClient(om_url, args.email, args.password)
    approve_repository_product(args.repo_path, client)


if __name__ == "__main__":
    main()
