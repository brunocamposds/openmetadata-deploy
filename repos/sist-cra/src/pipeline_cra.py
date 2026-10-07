"""
Pipeline Completo SIST_CRA (Job Kubernetes)
Execução: Cluster K3s via ClickHouse Server & OpenMetadata API
Camadas: CSV Seed -> Bronze (Auditoria) -> Silver -> Data Quality Tests -> Alertas OM
"""

import os
import sys
import time
import base64
import requests
from datetime import datetime, timezone
from pathlib import Path
import clickhouse_connect

# Configurações do ambiente ClickHouse
CH_HOST = os.getenv("CLICKHOUSE_SERVER_HOST", "clickhouse-server.openmetadata.svc.cluster.local")
CH_PORT = int(os.getenv("CLICKHOUSE_SERVER_PORT", "8123"))
CH_DB = os.getenv("CLICKHOUSE_DB", "investments")
CH_USER = os.getenv("CLICKHOUSE_USER", "clickhouse_user")
CH_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "clickhouse_password")

OM_URL = os.getenv("OPENMETADATA_URL", "http://openmetadata.openmetadata.svc.cluster.local:8585/api")
OM_USER = os.getenv("OPENMETADATA_ADMIN_EMAIL", "admin@open-metadata.org")
OM_PASSWORD = os.getenv("OPENMETADATA_ADMIN_PASSWORD", "admin")

# Resolução de paths dos seeds
BASE_DIR = Path(__file__).resolve().parent.parent
SEEDS_DIR = BASE_DIR / "seeds"

def get_om_token():
    for attempt in range(3):
        try:
            b64_pass = base64.b64encode(OM_PASSWORD.encode()).decode()
            login_url = f"{OM_URL.rstrip('/')}/v1/users/login"
            resp = requests.post(login_url, json={"email": OM_USER, "password": b64_pass}, timeout=15)
            if resp.status_code == 200:
                return resp.json().get("accessToken")
        except Exception as e:
            if attempt == 2:
                print(f"    [Aviso] Falha ao autenticar no OpenMetadata: {e}")
            time.sleep(2)
    return None

OM_TOKEN = get_om_token()

def parse_date(val: str):
    if not val:
        return None
    return datetime.strptime(val[:10], "%Y-%m-%d").date()

def parse_datetime(val: str):
    if not val:
        return None
    cleaned = val.replace('T', ' ').split('.')[0].replace('Z', '')
    return datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S")

def get_client():
    print(f">>> [SIST_CRA] Conectando ao ClickHouse Server em {CH_HOST}:{CH_PORT}...")
    for host, port in [(CH_HOST, CH_PORT), ("localhost", 8123)]:
        try:
            client = clickhouse_connect.get_client(host=host, port=port, username=CH_USER, password=CH_PASSWORD)
            return client
        except Exception:
            continue
    return clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)

def publish_test_result_to_om(test_name: str, table_fqn: str, passed: bool, message: str, row_count: int):
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    status_str = "Success" if passed else "Failed"
    print(f">>> [OM Observability] Reportando teste '{test_name}' para {table_fqn}: {status_str} ({message})")

    if not table_fqn.startswith("clickhouse_server.") and not table_fqn.startswith("mongodb_k3s."):
        full_table_fqn = f"clickhouse_server.{table_fqn}"
    else:
        full_table_fqn = table_fqn

    tc_fqn = f"{full_table_fqn}.{test_name}"

    if not OM_TOKEN:
        print("    [Info] Sem autenticação no OM. Teste avaliado localmente com sucesso.")
        return

    headers = {"Authorization": f"Bearer {OM_TOKEN}", "Content-Type": "application/json"}

    try:
        check = requests.get(f"{OM_URL.rstrip('/')}/v1/dataQuality/testCases/name/{tc_fqn}", headers=headers, timeout=5)
        if check.status_code != 200:
            entity_link = f"<#E::table::{full_table_fqn}>"
            requests.put(f"{OM_URL.rstrip('/')}/v1/dataQuality/testCases", headers=headers, json={
                "name": test_name,
                "displayName": test_name.replace("_", " ").title(),
                "description": f"Teste de Qualidade de Dados ODCS: {test_name}",
                "entityLink": entity_link,
                "testDefinition": "tableCustomSQLQuery",
                "parameterValues": [
                    {"name": "sqlExpression", "value": message}
                ]
            }, timeout=5)
    except Exception:
        pass

    try:
        url = f"{OM_URL.rstrip('/')}/v1/dataQuality/testCases/testCaseResults/{tc_fqn}"
        payload = {
            "timestamp": timestamp,
            "testCaseStatus": status_str,
            "result": message,
            "testResultValue": [
                {"name": "rowCount", "value": str(row_count)}
            ]
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code in (200, 201):
            print(f"    [OK] Alerta/Métrica registrada no OpenMetadata com sucesso!")
        else:
            print(f"    [Info] OM respondeu {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"    [Aviso] Falha de conexão com OM ao postar resultado: {e}")

def run_bronze_ingestion(client):
    print("\n--- 1. Ingestão da Camada Bronze (SIST_CRA) ---")
    client.command("CREATE DATABASE IF NOT EXISTS cra;")

    pos_seed = SEEDS_DIR / "cra_posicao_seed.csv"
    mov_seed = SEEDS_DIR / "cra_movimentacao_seed.csv"

    # 1.1 Bronze Posição
    client.command("""
        CREATE TABLE IF NOT EXISTS cra.bronze_posicao (
            id_posicao String,
            dt_posicao Date,
            cd_cra_isin String,
            nm_emissora_securitizadora String,
            id_cliente String,
            cd_tipo_remuneracao String,
            qt_titulos_custodia Int64,
            vl_principal_aplicado Decimal(18,2),
            vl_saldo_bruto Decimal(18,2),
            vl_saldo_liquido Decimal(18,2),
            dt_emissao Date,
            dt_vencimento Date,
            dh_ingestao_utc DateTime,
            _raw_file String,
            _ingested_at DateTime DEFAULT now(),
            _source_system String DEFAULT 'SIST_CRA_SECURITIZADORA_GATEWAY'
        ) ENGINE = MergeTree()
        ORDER BY id_posicao;
    """)

    client.command("TRUNCATE TABLE cra.bronze_posicao;")

    pos_rows = []
    with open(pos_seed, 'r', encoding='utf-8') as f:
        lines = f.readlines()[1:]
        for line in lines:
            parts = [p.strip() for p in line.strip().split(',')]
            if len(parts) >= 13:
                pos_rows.append([
                    parts[0], parse_date(parts[1]), parts[2], parts[3], parts[4],
                    parts[5], int(parts[6]), float(parts[7]), float(parts[8]), float(parts[9]),
                    parse_date(parts[10]), parse_date(parts[11]), parse_datetime(parts[12]),
                    pos_seed.name
                ])

    if pos_rows:
        client.insert(
            "cra.bronze_posicao",
            pos_rows,
            column_names=[
                "id_posicao", "dt_posicao", "cd_cra_isin", "nm_emissora_securitizadora",
                "id_cliente", "cd_tipo_remuneracao", "qt_titulos_custodia", "vl_principal_aplicado",
                "vl_saldo_bruto", "vl_saldo_liquido", "dt_emissao", "dt_vencimento",
                "dh_ingestao_utc", "_raw_file"
            ]
        )

    # 1.2 Bronze Movimentação
    client.command("""
        CREATE TABLE IF NOT EXISTS cra.bronze_movimentacao (
            id_movimentacao String,
            dt_movimentacao Date,
            cd_cra_isin String,
            id_cliente String,
            tp_movimentacao String,
            qt_titulos Int64,
            vl_financeiro_movimentado Decimal(18,2),
            dh_processamento_utc DateTime,
            _raw_file String,
            _ingested_at DateTime DEFAULT now(),
            _source_system String DEFAULT 'SIST_CRA_SECURITIZADORA_GATEWAY'
        ) ENGINE = MergeTree()
        ORDER BY id_movimentacao;
    """)

    client.command("TRUNCATE TABLE cra.bronze_movimentacao;")

    mov_rows = []
    with open(mov_seed, 'r', encoding='utf-8') as f:
        lines = f.readlines()[1:]
        for line in lines:
            parts = [p.strip() for p in line.strip().split(',')]
            if len(parts) >= 8:
                mov_rows.append([
                    parts[0], parse_date(parts[1]), parts[2], parts[3], parts[4],
                    int(parts[5]), float(parts[6]),
                    parse_datetime(parts[7]),
                    mov_seed.name
                ])

    if mov_rows:
        client.insert(
            "cra.bronze_movimentacao",
            mov_rows,
            column_names=[
                "id_movimentacao", "dt_movimentacao", "cd_cra_isin", "id_cliente",
                "tp_movimentacao", "qt_titulos", "vl_financeiro_movimentado",
                "dh_processamento_utc", "_raw_file"
            ]
        )

    c_pos = client.query("SELECT count() FROM cra.bronze_posicao").result_rows[0][0]
    c_mov = client.query("SELECT count() FROM cra.bronze_movimentacao").result_rows[0][0]
    print(f">>> [SIST_CRA] Bronze concluída! Registros: {c_pos} posições, {c_mov} movimentações.")

def run_silver_transformation(client):
    print("\n--- 2. Transformação da Camada Silver (SIST_CRA) ---")

    # 2.1 Silver Posição
    client.command("""
        CREATE TABLE IF NOT EXISTS cra.silver_posicao (
            id_posicao String,
            dt_posicao Date,
            cd_cra_isin String,
            nm_emissora_securitizadora String,
            id_cliente String,
            cd_tipo_remuneracao String,
            qt_titulos_custodia Int64,
            vl_principal_aplicado Decimal(18,2),
            vl_saldo_bruto Decimal(18,2),
            vl_saldo_liquido Decimal(18,2),
            dt_emissao Date,
            dt_vencimento Date,
            dh_ingestao_utc DateTime
        ) ENGINE = ReplacingMergeTree()
        ORDER BY id_posicao;
    """)

    client.command("TRUNCATE TABLE cra.silver_posicao;")

    client.command("""
        INSERT INTO cra.silver_posicao
        SELECT
            id_posicao, dt_posicao, cd_cra_isin, nm_emissora_securitizadora,
            id_cliente, cd_tipo_remuneracao, qt_titulos_custodia, vl_principal_aplicado,
            vl_saldo_bruto, vl_saldo_liquido, dt_emissao, dt_vencimento, dh_ingestao_utc
        FROM cra.bronze_posicao;
    """)

    # 2.2 Silver Movimentação
    client.command("""
        CREATE TABLE IF NOT EXISTS cra.silver_movimentacao (
            id_movimentacao String,
            dt_movimentacao Date,
            cd_cra_isin String,
            id_cliente String,
            tp_movimentacao String,
            qt_titulos Int64,
            vl_financeiro_movimentado Decimal(18,2),
            dh_processamento_utc DateTime
        ) ENGINE = ReplacingMergeTree()
        ORDER BY id_movimentacao;
    """)

    client.command("TRUNCATE TABLE cra.silver_movimentacao;")

    client.command("""
        INSERT INTO cra.silver_movimentacao
        SELECT
            id_movimentacao, dt_movimentacao, cd_cra_isin, id_cliente,
            tp_movimentacao, qt_titulos, vl_financeiro_movimentado, dh_processamento_utc
        FROM cra.bronze_movimentacao;
    """)

    c_pos = client.query("SELECT count() FROM cra.silver_posicao").result_rows[0][0]
    print(f">>> [SIST_CRA] Silver concluída! Registros na silver_posicao: {c_pos}")

def run_quality_checks_and_observability(client):
    print("\n--- 3. Execução dos Testes de Qualidade ODCS & Observabilidade ---")

    # Teste 1: check_saldo_positivo_cra
    violations = client.query("SELECT count() FROM cra.silver_posicao WHERE vl_saldo_bruto < 0 OR vl_saldo_liquido < 0").result_rows[0][0]
    passed = (violations == 0)
    msg = f"Saldos de CRA positivos e válidos" if passed else f"{violations} posições com saldos negativos!"
    publish_test_result_to_om("check_saldo_positivo_cra", "clickhouse_server.investments.cra.silver_posicao", passed, msg, violations)

    # Teste 2: check_qt_titulos_positiva_cra
    violations = client.query("SELECT count() FROM cra.silver_posicao WHERE qt_titulos_custodia <= 0").result_rows[0][0]
    passed = (violations == 0)
    msg = f"Quantidade de títulos em custódia estritamente positiva" if passed else f"{violations} registros com títulos zerados!"
    publish_test_result_to_om("check_qt_titulos_positiva_cra", "clickhouse_server.investments.cra.silver_posicao", passed, msg, violations)

    # Teste 3: check_consistencia_liquido_bruto_cra
    violations = client.query("SELECT count() FROM cra.silver_posicao WHERE vl_saldo_liquido > vl_saldo_bruto").result_rows[0][0]
    passed = (violations == 0)
    msg = f"Consistência OK (líquido <= bruto para CRA)" if passed else f"{violations} violações de saldo!"
    publish_test_result_to_om("check_consistencia_liquido_bruto_cra", "clickhouse_server.investments.cra.silver_posicao", passed, msg, violations)

def main():
    print("=" * 65)
    print("EXECUTANDO PIPELINE K3S: SIST_CRA (ClickHouse)")
    print("=" * 65)
    client = get_client()
    try:
        run_bronze_ingestion(client)
        run_silver_transformation(client)
        run_quality_checks_and_observability(client)
        print("\n" + "=" * 65)
        print("PIPELINE SIST_CRA FINALIZADO COM SUCESSO!")
        print("=" * 65)
    finally:
        client.close()

if __name__ == "__main__":
    main()
