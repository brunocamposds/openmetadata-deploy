#!/usr/bin/env python3
"""
==============================================================================
Script de Reset Completo do OpenMetadata & Ambientes de Dados
==============================================================================
Restaura o OpenMetadata e os bancos de dados DuckDB e MongoDB para o estado
limpo de 'recém-instalado':
1. Deleta Data Products (SIST_CDB, SIST_CRA, RENDA_FIXA_DERIVADO)
2. Deleta Contratos ODCS e Testes de Qualidade de Dados (Observabilidade)
3. Deleta Serviços de Banco (duckdb_server, mongodb_k3s, origens Oracle/Db2)
4. Deleta Domínios, Subdomínios e Termos de Glossário de Investimentos
5. Deleta Squads customizadas e Subscriptions de Alertas
6. Limpa todas as threads e notificações do Activity Feed / Sininho
7. Reseta os schemas nos bancos físicos (DuckDB: cdb, cra, renda_fixa; MongoDB: investments_serving)
8. Remove pods de Jobs concluídos do K3s
==============================================================================
"""

import sys
import os
import base64
import requests
import psycopg2

BOLD = "\033[1m"
GREEN = "\033[0;32m"
CYAN = "\033[0;36m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
RESET = "\033[0m"


def get_om_client():
    om_candidates = [
        os.getenv("OPENMETADATA_URL", "").rstrip("/"),
        "http://localhost:8585/api",
        "http://localhost/api",
        "http://openmetadata.openmetadata.svc.cluster.local:8585/api"
    ]
    base_url = None
    for cand in om_candidates:
        if not cand:
            continue
        try:
            r = requests.get(f"{cand}/v1/system/version", timeout=3)
            if r.status_code == 200:
                base_url = cand
                break
        except Exception:
            continue

    if not base_url:
        print(f"{RED}Erro: Não foi possível conectar à API do OpenMetadata em nenhum endpoint conhecido.{RESET}")
        sys.exit(1)

    email = os.getenv("OPENMETADATA_ADMIN_EMAIL", "admin@open-metadata.org")
    password = os.getenv("OPENMETADATA_ADMIN_PASSWORD", "admin")
    b64_pass = base64.b64encode(password.encode()).decode()

    login_resp = requests.post(f"{base_url}/v1/users/login", json={"email": email, "password": b64_pass}, timeout=10)
    if login_resp.status_code != 200:
        print(f"{RED}Erro de autenticação no OpenMetadata ({login_resp.status_code}): {login_resp.text}{RESET}")
        sys.exit(1)

    token = login_resp.json()["accessToken"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    return base_url, headers


def reset_openmetadata_catalog(base_url, headers):
    print(f"\n{BOLD}{CYAN}>>> [1/5] Limpando Entidades de Governança no OpenMetadata...{RESET}")

    # 1. Deletar Data Products
    try:
        dps = requests.get(f"{base_url}/v1/dataProducts?limit=100", headers=headers, timeout=10).json().get("data", [])
        for dp in dps:
            dp_id = dp["id"]
            dp_name = dp.get("name")
            r = requests.delete(f"{base_url}/v1/dataProducts/{dp_id}?hardDelete=true", headers=headers, timeout=10)
            if r.status_code in (200, 204):
                print(f"  {GREEN}✔ Data Product removido:{RESET} {dp_name}")
    except Exception as e:
        print(f"  {YELLOW}Aviso ao remover Data Products: {e}{RESET}")

    # 2. Deletar Data Contracts
    try:
        contracts = requests.get(f"{base_url}/v1/dataContracts?limit=100", headers=headers, timeout=10).json().get("data", [])
        for c in contracts:
            c_id = c["id"]
            c_name = c.get("name", c_id)
            r = requests.delete(f"{base_url}/v1/dataContracts/{c_id}?hardDelete=true", headers=headers, timeout=10)
            if r.status_code in (200, 204):
                print(f"  {GREEN}✔ Contrato ODCS removido:{RESET} {c_name}")
    except Exception as e:
        print(f"  {YELLOW}Aviso ao remover Contratos: {e}{RESET}")

    # 3. Deletar Test Cases e Test Suites
    try:
        tcs = requests.get(f"{base_url}/v1/dataQuality/testCases?limit=100", headers=headers, timeout=10).json().get("data", [])
        for tc in tcs:
            tc_id = tc["id"]
            requests.delete(f"{base_url}/v1/dataQuality/testCases/{tc_id}?hardDelete=true&recursive=true", headers=headers, timeout=10)
        print(f"  {GREEN}✔ Test Cases de Qualidade/Observabilidade removidos ({len(tcs)} testes).{RESET}")
    except Exception as e:
        print(f"  {YELLOW}Aviso ao remover Test Cases: {e}{RESET}")

    # 4. Deletar Serviços de Banco (DuckDB, MongoDB, Origens)
    target_services = ["duckdb_server", "mongodb_k3s", "sist_cdb_oracle_core", "sist_cra_securitizadora_gateway"]
    for svc_name in target_services:
        try:
            svc = requests.get(f"{base_url}/v1/services/databaseServices/name/{svc_name}", headers=headers, timeout=10).json()
            svc_id = svc.get("id")
            if svc_id:
                r = requests.delete(f"{base_url}/v1/services/databaseServices/{svc_id}?recursive=true&hardDelete=true", headers=headers, timeout=15)
                if r.status_code in (200, 204):
                    print(f"  {GREEN}✔ Serviço de Banco removido:{RESET} {svc_name}")
        except Exception as e:
            pass

    # 5. Deletar Glossários de Negócio
    target_glossaries = ["Investimentos"]
    for gloss in target_glossaries:
        try:
            g = requests.get(f"{base_url}/v1/glossaries/name/{gloss}", headers=headers, timeout=10).json()
            g_id = g.get("id")
            if g_id:
                r = requests.delete(f"{base_url}/v1/glossaries/{g_id}?recursive=true&hardDelete=true", headers=headers, timeout=15)
                if r.status_code in (200, 204):
                    print(f"  {GREEN}✔ Glossário Corporativo removido:{RESET} {gloss}")
        except Exception:
            pass

    # 6. Deletar Domínios e Subdomínios
    try:
        domains = requests.get(f"{base_url}/v1/domains?limit=100", headers=headers, timeout=10).json().get("data", [])
        for d in domains:
            d_name = d.get("name")
            d_id = d.get("id")
            if d_name in ("Investimentos", "EmissoesBancarias", "Securitizacao", "RendaFixa"):
                r = requests.delete(f"{base_url}/v1/domains/{d_id}?recursive=true&hardDelete=true", headers=headers, timeout=15)
                if r.status_code in (200, 204):
                    print(f"  {GREEN}✔ Domínio removido:{RESET} {d_name}")
    except Exception as e:
        print(f"  {YELLOW}Aviso ao remover Domínios: {e}{RESET}")

    # 7. Deletar Squads / Times Customizados
    target_teams = ["squad-cdb", "squad-cra", "squad-derivados"]
    for t_name in target_teams:
        try:
            t = requests.get(f"{base_url}/v1/teams/name/{t_name}", headers=headers, timeout=10).json()
            t_id = t.get("id")
            if t_id:
                r = requests.delete(f"{base_url}/v1/teams/{t_id}?hardDelete=true", headers=headers, timeout=10)
                if r.status_code in (200, 204):
                    print(f"  {GREEN}✔ Squad removida:{RESET} {t_name}")
        except Exception:
            pass

    # 8. Deletar Subscriptions de Observabilidade Customizadas
    try:
        subs = requests.get(f"{base_url}/v1/events/subscriptions?limit=100", headers=headers, timeout=10).json().get("data", [])
        for s in subs:
            s_name = s.get("name")
            if s_name == "DataQualityObservabilityAlert":
                requests.delete(f"{base_url}/v1/events/subscriptions/{s['id']}?hardDelete=true", headers=headers, timeout=10)
                print(f"  {GREEN}✔ Alerta de Observabilidade removido:{RESET} {s_name}")
    except Exception:
        pass

    # 9. Limpar Threads e Notificações do Feed / Sininho
    try:
        feeds = requests.get(f"{base_url}/v1/feed?limit=100", headers=headers, timeout=10).json().get("data", [])
        deleted_count = 0
        for f_item in feeds:
            f_id = f_item.get("id")
            if f_id:
                requests.delete(f"{base_url}/v1/feed/{f_id}", headers=headers, timeout=5)
                deleted_count += 1
        print(f"  {GREEN}✔ Feeds e Notificações do Sininho limpos ({deleted_count} itens removidos).{RESET}")
    except Exception as e:
        print(f"  {YELLOW}Aviso ao limpar Feed: {e}{RESET}")


def reset_duckdb_server():
    print(f"\n{BOLD}{CYAN}>>> [2/5] Limpando Schemas no DuckDB Server (investments.duckdb)...{RESET}")
    endpoints = [
        ("duckdb-server.openmetadata.svc.cluster.local", 5433),
        ("localhost", 5433)
    ]
    connected = False
    for host, port in endpoints:
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                dbname="investments",
                user="duckdb_user",
                password="duckdb_password",
                connect_timeout=3
            )
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("""
                DROP SCHEMA IF EXISTS cdb CASCADE;
                DROP SCHEMA IF EXISTS cra CASCADE;
                DROP SCHEMA IF EXISTS renda_fixa CASCADE;
            """)
            conn.close()
            print(f"  {GREEN}✔ Schemas 'cdb', 'cra' e 'renda_fixa' eliminados no DuckDB Server ({host}:{port}).{RESET}")
            connected = True
            break
        except Exception:
            continue

    if not connected:
        # Fallback via kubectl exec se fora do cluster
        import subprocess
        try:
            cmd = "kubectl exec -n openmetadata deployment/duckdb-server -- psql -U duckdb_user -d investments -p 5433 -c 'DROP SCHEMA IF EXISTS cdb CASCADE; DROP SCHEMA IF EXISTS cra CASCADE; DROP SCHEMA IF EXISTS renda_fixa CASCADE;'"
            subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"  {GREEN}✔ Schemas eliminados no DuckDB Server via kubectl exec.{RESET}")
        except Exception as e:
            print(f"  {YELLOW}Aviso ao resetar DuckDB: {e}{RESET}")


def reset_mongodb_collections():
    print(f"\n{BOLD}{CYAN}>>> [3/5] Limpando Coleções no MongoDB (investments_serving)...{RESET}")
    import subprocess
    try:
        cmd = "kubectl exec -n openmetadata deployment/mongodb -- mongosh --quiet --eval 'db.getSiblingDB(\"investments_serving\").dropDatabase()'"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            print(f"  {GREEN}✔ Banco operacional 'investments_serving' eliminado no MongoDB.{RESET}")
        else:
            print(f"  {YELLOW}Aviso MongoDB: {res.stderr.strip()}{RESET}")
    except Exception as e:
        print(f"  {YELLOW}Aviso ao resetar MongoDB: {e}{RESET}")


def clean_k8s_jobs():
    print(f"\n{BOLD}{CYAN}>>> [4/5] Removendo Jobs e Pods Concluídos no K3s...{RESET}")
    import subprocess
    try:
        cmd = "kubectl delete job pipeline-cdb pipeline-cra pipeline-renda-fixa -n openmetadata --ignore-not-found=true"
        subprocess.run(cmd, shell=True, check=True)
        print(f"  {GREEN}✔ Jobs de pipelines removidos do namespace openmetadata.{RESET}")
    except Exception as e:
        print(f"  {YELLOW}Aviso ao limpar Jobs: {e}{RESET}")


def reindex_opensearch(base_url, headers):
    print(f"\n{BOLD}{CYAN}>>> [5/5] Reindexando OpenSearch para sincronização do catálogo limpo...{RESET}")
    try:
        requests.post(f"{base_url}/v1/search/reindex?force=true", headers=headers, timeout=10)
        print(f"  {GREEN}✔ Reindexação do catálogo disparada com sucesso.{RESET}")
    except Exception:
        pass


def main():
    print(f"\n{BOLD}{RED}{'='*80}{RESET}")
    print(f"{BOLD}{RED}   RESET COMPLETO: RESTAURANDO OPENMETADATA PARA ESTADO RECÉM-INSTALADO     {RESET}")
    print(f"{BOLD}{RED}{'='*80}{RESET}")

    base_url, headers = get_om_client()
    print(f"{CYAN}Conectado à API do OpenMetadata em:{RESET} {BOLD}{base_url}{RESET}")

    reset_openmetadata_catalog(base_url, headers)
    reset_duckdb_server()
    reset_mongodb_collections()
    clean_k8s_jobs()
    reindex_opensearch(base_url, headers)

    print(f"\n{BOLD}{GREEN}{'='*80}{RESET}")
    print(f"{BOLD}{GREEN}   ✔ OPENMETADATA E BANCOS ZERADOS COM SUCESSO!                             {RESET}")
    print(f"{BOLD}{GREEN}   O ambiente está pronto para uma nova demonstração do início.             {RESET}")
    print(f"{BOLD}{GREEN}{'='*80}{RESET}\n")


if __name__ == "__main__":
    main()
