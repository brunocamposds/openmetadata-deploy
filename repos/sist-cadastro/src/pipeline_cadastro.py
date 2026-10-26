"""
Pipeline Completo SIST_CADASTRO (Job Kubernetes / Local)
Execução: Cluster K3s via ClickHouse Server & OpenMetadata API
Produto de Dados: SIST_CADASTRO (Master Data Management - Clientes)
Tabela: cadastro.clientes (De/Para MDM)
"""

import os
import sys
import time
import base64
import csv
from datetime import datetime, timezone
from pathlib import Path
import requests
import clickhouse_connect

# Configurações do ambiente ClickHouse
CH_HOST = os.getenv("CLICKHOUSE_SERVER_HOST", "clickhouse-server.openmetadata.svc.cluster.local")
CH_PORT = int(os.getenv("CLICKHOUSE_SERVER_PORT", "8123"))
CH_USER = os.getenv("CLICKHOUSE_USER", "clickhouse_user")
CH_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "clickhouse_password")

OM_USER = os.getenv("OPENMETADATA_ADMIN_EMAIL", "admin@open-metadata.org")
OM_PASSWORD = os.getenv("OPENMETADATA_ADMIN_PASSWORD", "admin")

BASE_DIR = Path(__file__).resolve().parent.parent
SEEDS_DIR = BASE_DIR / "seeds"

def resolve_om_url():
    env_url = os.getenv("OPENMETADATA_URL")
    candidates = [env_url] if env_url else []
    candidates.extend([
        "http://openmetadata.openmetadata.svc.cluster.local:8585/api",
        "http://localhost:8585/api",
        "http://openmetadata.local/api",
        "http://localhost/api"
    ])
    for c in candidates:
        if not c:
            continue
        try:
            r = requests.get(f"{c.rstrip('/')}/v1/system/version", timeout=2)
            if r.status_code == 200:
                return c
        except Exception:
            continue
    return "http://localhost:8585/api"


ACTUAL_OM_URL = resolve_om_url()


def get_om_token():
    for attempt in range(3):
        try:
            b64_pass = base64.b64encode(OM_PASSWORD.encode()).decode()
            login_url = f"{ACTUAL_OM_URL.rstrip('/')}/v1/users/login"
            resp = requests.post(login_url, json={"email": OM_USER, "password": b64_pass}, timeout=15)
            if resp.status_code == 200:
                return resp.json().get("accessToken")
        except Exception as e:
            if attempt == 2:
                print(f"    [Aviso] Falha ao autenticar no OpenMetadata: {e}")
            time.sleep(2)
    return None


OM_TOKEN = get_om_token()


def get_client():
    print(f">>> [SIST_CADASTRO] Conectando ao ClickHouse Server em {CH_HOST}:{CH_PORT}...")
    for host, port in [(CH_HOST, CH_PORT), ("localhost", 8123)]:
        try:
            client = clickhouse_connect.get_client(host=host, port=port, username=CH_USER, password=CH_PASSWORD)
            return client
        except Exception:
            continue
    return clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)


def publish_test_result_to_om(test_name: str, table_fqn: str, passed: bool, message: str, row_count: int):
    """Envia resultado do teste para a API do OpenMetadata para observabilidade e alertas."""
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    status_str = "Success" if passed else "Failed"
    print(f">>> [OM Observability] Reportando teste '{test_name}' para {table_fqn}: {status_str} ({message})")

    if not table_fqn.startswith("clickhouse_server."):
        full_table_fqn = f"clickhouse_server.{table_fqn}"
    else:
        full_table_fqn = table_fqn

    tc_fqn = f"{full_table_fqn}.{test_name}"

    if not OM_TOKEN:
        print("    [Info] Sem autenticação no OM. Teste avaliado localmente.")
        return

    headers = {"Authorization": f"Bearer {OM_TOKEN}", "Content-Type": "application/json"}

    # 1. Garantir que o TestCase existe no OpenMetadata
    try:
        check = requests.get(f"{ACTUAL_OM_URL.rstrip('/')}/v1/dataQuality/testCases/name/{tc_fqn}", headers=headers, timeout=5)
        if check.status_code != 200:
            entity_link = f"<#E::table::{full_table_fqn}>"
            requests.put(f"{ACTUAL_OM_URL.rstrip('/')}/v1/dataQuality/testCases", headers=headers, json={
                "name": test_name,
                "displayName": test_name.replace("_", " ").title(),
                "description": f"Teste de Qualidade de Dados ODCS MDM: {test_name}",
                "entityLink": entity_link,
                "testDefinition": "tableCustomSQLQuery",
                "parameterValues": [
                    {"name": "sqlExpression", "value": message}
                ]
            }, timeout=10)
    except Exception as e:
        print(f"    [Aviso] Falha ao registrar testCase {tc_fqn}: {e}")

    # 2. Publicar resultado do teste
    try:
        res_payload = {
            "timestamp": timestamp,
            "testCaseStatus": status_str,
            "result": f"Linhas avaliadas: {row_count} | Status: {status_str} | Detalhe: {message}",
            "testResultValue": [
                {"name": "rowCount", "value": str(row_count)},
                {"name": "passed", "value": str(passed)}
            ]
        }
        resp = requests.put(f"{ACTUAL_OM_URL.rstrip('/')}/v1/dataQuality/testCases/{tc_fqn}/testCaseResult",
                            headers=headers, json=res_payload, timeout=10)
        if resp.status_code in (200, 201):
            print(f"    [✔] Alerta/Resultado registrado com sucesso no OpenMetadata!")
    except Exception as e:
        print(f"    [Aviso] Falha ao publicar testCaseResult: {e}")


def main():
    print("=" * 80)
    print("SIST_CADASTRO - Pipeline de Master Data Management (MDM Clientes)")
    print("=" * 80)

    client = get_client()

    # 1. Criar bancos de dados
    client.command("CREATE DATABASE IF NOT EXISTS cadastro")
    client.command("CREATE DATABASE IF NOT EXISTS investments")

    # 2. Criar tabela de clientes no schema cadastro
    print(">>> [SIST_CADASTRO] Provisionando tabela cadastro.clientes no ClickHouse...")
    client.command("""
    CREATE TABLE IF NOT EXISTS cadastro.clientes (
        id_cliente_global String,
        id_cliente_legado String,
        cpf_cnpj_hash String,
        nome_cliente String,
        tipo_pessoa LowCardinality(String),
        status_cadastro LowCardinality(String),
        dt_cadastro Date,
        dh_ingestao_utc DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    ORDER BY (id_cliente_global, id_cliente_legado)
    """)

    # Também criamos a view / tabela de compatibilidade em investments.cadastro_clientes
    client.command("""
    CREATE TABLE IF NOT EXISTS investments.cadastro_clientes (
        id_cliente_global String,
        id_cliente_legado String,
        cpf_cnpj_hash String,
        nome_cliente String,
        tipo_pessoa LowCardinality(String),
        status_cadastro LowCardinality(String),
        dt_cadastro Date,
        dh_ingestao_utc DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    ORDER BY (id_cliente_global, id_cliente_legado)
    """)

    # 3. Carregar seed CSV
    seed_file = SEEDS_DIR / "cadastro_clientes_seed.csv"
    if not seed_file.exists():
        print(f"Erro: Arquivo seed não encontrado em {seed_file}")
        sys.exit(1)

    print(f">>> [SIST_CADASTRO] Lendo seed {seed_file.name}...")
    rows_to_insert = []
    with open(seed_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dt = datetime.strptime(row["dt_cadastro"].strip(), "%Y-%m-%d").date()
            rows_to_insert.append([
                row["id_cliente_global"].strip(),
                row["id_cliente_legado"].strip(),
                row["cpf_cnpj_hash"].strip(),
                row["nome_cliente"].strip(),
                row["tipo_pessoa"].strip(),
                row["status_cadastro"].strip(),
                dt,
                datetime.now(timezone.utc).replace(tzinfo=None)
            ])

    # Truncate para carga idempotente
    client.command("TRUNCATE TABLE cadastro.clientes")
    client.command("TRUNCATE TABLE investments.cadastro_clientes")

    columns = [
        "id_cliente_global", "id_cliente_legado", "cpf_cnpj_hash",
        "nome_cliente", "tipo_pessoa", "status_cadastro",
        "dt_cadastro", "dh_ingestao_utc"
    ]
    client.insert("cadastro.clientes", rows_to_insert, column_names=columns)
    client.insert("investments.cadastro_clientes", rows_to_insert, column_names=columns)

    total_inserted = len(rows_to_insert)
    print(f"✔ [SIST_CADASTRO] Inseridas {total_inserted} linhas em cadastro.clientes e investments.cadastro_clientes com sucesso!")

    # 4. Testes de Qualidade de Dados (Data Quality / ODCS)
    print("\n>>> [SIST_CADASTRO] Executando Testes de Qualidade de Dados (ODCS)...")
    table_target_fqn = "investments.cadastro.clientes"

    # Teste 1: Unicidade da Chave Global
    dups = client.command("""
        SELECT count() FROM (
            SELECT id_cliente_global, count() as cnt 
            FROM cadastro.clientes 
            GROUP BY id_cliente_global 
            HAVING cnt > 1
        )
    """)
    t1_pass = (dups == 0)
    publish_test_result_to_om(
        test_name="test_clientes_unicidade_chave_global",
        table_fqn=table_target_fqn,
        passed=t1_pass,
        message="Chave id_cliente_global 100% unica no cadastro MDM" if t1_pass else f"Duplicidades encontradas: {dups}",
        row_count=total_inserted
    )

    # Teste 2: Não Nulidade dos Campos Críticos
    nulls = client.command("""
        SELECT count() FROM cadastro.clientes
        WHERE id_cliente_global IS NULL OR id_cliente_global = ''
           OR id_cliente_legado IS NULL OR id_cliente_legado = ''
           OR cpf_cnpj_hash IS NULL OR cpf_cnpj_hash = ''
    """)
    t2_pass = (nulls == 0)
    publish_test_result_to_om(
        test_name="test_clientes_nao_nulos",
        table_fqn=table_target_fqn,
        passed=t2_pass,
        message="Nenhum valor nulo ou vazio encontrado nos campos criticos" if t2_pass else f"Nulos encontrados: {nulls}",
        row_count=total_inserted
    )

    # Teste 3: Conformidade de Domínio - Status Cadastral
    invalid_status = client.command("""
        SELECT count() FROM cadastro.clientes
        WHERE status_cadastro NOT IN ('ATIVO', 'BLOQUEADO', 'CANCELADO')
    """)
    t3_pass = (invalid_status == 0)
    publish_test_result_to_om(
        test_name="test_clientes_status_valido",
        table_fqn=table_target_fqn,
        passed=t3_pass,
        message="Todos os status estao em conformidade com o enum regulatorio" if t3_pass else f"Status invalidos: {invalid_status}",
        row_count=total_inserted
    )

    # Teste 4: Conformidade de Tipo de Pessoa
    invalid_tp = client.command("""
        SELECT count() FROM cadastro.clientes
        WHERE tipo_pessoa NOT IN ('PF', 'PJ')
    """)
    t4_pass = (invalid_tp == 0)
    publish_test_result_to_om(
        test_name="test_clientes_tipo_pessoa_valido",
        table_fqn=table_target_fqn,
        passed=t4_pass,
        message="Tipos de pessoa 100% compativeis (PF/PJ)" if t4_pass else f"Tipos invalidos: {invalid_tp}",
        row_count=total_inserted
    )

    print("\n" + "=" * 80)
    print("✔ Pipeline SIST_CADASTRO concluído com sucesso!")
    print("=" * 80)


if __name__ == "__main__":
    main()
