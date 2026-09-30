"""
Pipeline Completo SIST_CDB (Job Kubernetes)
Execução: Cluster K3s via DuckDB Server & OpenMetadata API
Camadas: CSV Seed -> Bronze (Auditoria) -> Silver -> Data Quality Tests -> Alertas OM
"""

import os
import sys
import time
import base64
import psycopg2
import requests
from datetime import datetime, timezone
from pathlib import Path

# Configurações do ambiente
DB_HOST = os.getenv("DUCKDB_SERVER_HOST", "duckdb-server.openmetadata.svc.cluster.local")
DB_PORT = int(os.getenv("DUCKDB_SERVER_PORT", "5433"))
DB_NAME = os.getenv("DUCKDB_DB", "investments")
DB_USER = os.getenv("DUCKDB_USER", "duckdb_user")
DB_PASSWORD = os.getenv("DUCKDB_PASSWORD", "duckdb_password")
OM_URL = os.getenv("OPENMETADATA_URL", "http://openmetadata.openmetadata.svc.cluster.local:8585/api")
OM_USER = os.getenv("OPENMETADATA_ADMIN_EMAIL", "admin@open-metadata.org")
OM_PASSWORD = os.getenv("OPENMETADATA_ADMIN_PASSWORD", "admin")

# Resolução de paths dos seeds
BASE_DIR = Path(__file__).resolve().parent.parent
SEEDS_DIR = BASE_DIR / "seeds"

def get_om_token():
    try:
        b64_pass = base64.b64encode(OM_PASSWORD.encode()).decode()
        login_url = f"{OM_URL.rstrip('/')}/v1/users/login"
        resp = requests.post(login_url, json={"email": OM_USER, "password": b64_pass}, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("accessToken")
    except Exception as e:
        print(f"    [Aviso] Falha ao autenticar no OpenMetadata: {e}")
    return None

OM_TOKEN = get_om_token()

def get_connection():
    print(f">>> [SIST_CDB] Conectando ao DuckDB Server em {DB_HOST}:{DB_PORT}/{DB_NAME}...")
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    conn.autocommit = True
    return conn

def publish_test_result_to_om(test_name: str, table_fqn: str, passed: bool, message: str, row_count: int):
    """Envia resultado do teste para a API do OpenMetadata para observabilidade e alertas."""
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    status_str = "Success" if passed else "Failed"
    print(f">>> [OM Observability] Reportando teste '{test_name}' para {table_fqn}: {status_str} ({message})")

    # Garante prefixo duckdb_server se não informado
    if not table_fqn.startswith("duckdb_server.") and not table_fqn.startswith("mongodb_k3s."):
        full_table_fqn = f"duckdb_server.{table_fqn}"
    else:
        full_table_fqn = table_fqn

    tc_fqn = f"{full_table_fqn}.{test_name}"

    if not OM_TOKEN:
        print("    [Info] Sem autenticação no OM. Teste avaliado localmente com sucesso.")
        return

    headers = {"Authorization": f"Bearer {OM_TOKEN}", "Content-Type": "application/json"}

    # 1. Garantir que o TestCase existe no OpenMetadata
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

    # 2. Publicar resultado do teste no endpoint correto
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

def run_bronze_ingestion(conn):
    print("\n--- 1. Ingestão da Camada Bronze (SIST_CDB) ---")
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS cdb;")

    pos_seed = SEEDS_DIR / "cdb_posicao_seed.csv"
    mov_seed = SEEDS_DIR / "cdb_movimentacao_seed.csv"

    # 1.1 Bronze Posição
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cdb.bronze_posicao (
            id_posicao VARCHAR(100),
            dt_posicao DATE,
            cd_certificado VARCHAR(100),
            id_cliente VARCHAR(100),
            cd_tipo_cdb VARCHAR(50),
            vl_principal_aplicado NUMERIC(18,2),
            vl_saldo_bruto NUMERIC(18,2),
            vl_saldo_liquido NUMERIC(18,2),
            tx_remuneracao NUMERIC(8,4),
            dt_aplicacao DATE,
            dt_vencimento DATE,
            dh_ingestao_utc TIMESTAMP,
            _raw_file VARCHAR(255),
            _ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            _source_system VARCHAR(100) DEFAULT 'SIST_CDB_ORACLE_CORE'
        );
    """)

    # Leitura e inserção do CSV
    with open(pos_seed, 'r', encoding='utf-8') as f:
        lines = f.readlines()[1:] # pula header
        for line in lines:
            parts = [p.strip() for p in line.strip().split(',')]
            if len(parts) >= 12:
                cur.execute("""
                    INSERT INTO cdb.bronze_posicao (
                        id_posicao, dt_posicao, cd_certificado, id_cliente, cd_tipo_cdb,
                        vl_principal_aplicado, vl_saldo_bruto, vl_saldo_liquido, tx_remuneracao,
                        dt_aplicacao, dt_vencimento, dh_ingestao_utc, _raw_file
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (parts[0], parts[1], parts[2], parts[3], parts[4],
                      parts[5], parts[6], parts[7], parts[8], parts[9],
                      parts[10], parts[11], pos_seed.name))

    # 1.2 Bronze Movimentação
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cdb.bronze_movimentacao (
            id_movimentacao VARCHAR(100),
            dt_movimentacao DATE,
            cd_certificado VARCHAR(100),
            id_cliente VARCHAR(100),
            tp_movimentacao VARCHAR(50),
            vl_movimentacao NUMERIC(18,2),
            vl_iof NUMERIC(18,2),
            vl_ir NUMERIC(18,2),
            vl_liquido_movimentado NUMERIC(18,2),
            dh_liquidacao_utc TIMESTAMP,
            _raw_file VARCHAR(255),
            _ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            _source_system VARCHAR(100) DEFAULT 'SIST_CDB_ORACLE_CORE'
        );
    """)

    with open(mov_seed, 'r', encoding='utf-8') as f:
        lines = f.readlines()[1:]
        for line in lines:
            parts = [p.strip() for p in line.strip().split(',')]
            if len(parts) >= 10:
                cur.execute("""
                    INSERT INTO cdb.bronze_movimentacao (
                        id_movimentacao, dt_movimentacao, cd_certificado, id_cliente,
                        tp_movimentacao, vl_movimentacao, vl_iof, vl_ir,
                        vl_liquido_movimentado, dh_liquidacao_utc, _raw_file
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (parts[0], parts[1], parts[2], parts[3], parts[4],
                      parts[5], parts[6], parts[7], parts[8], parts[9], mov_seed.name))

    cur.execute("SELECT COUNT(*) FROM cdb.bronze_posicao;")
    c_pos = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM cdb.bronze_movimentacao;")
    c_mov = cur.fetchone()[0]
    print(f">>> [SIST_CDB] Bronze concluída! Registros: {c_pos} posições, {c_mov} movimentações.")

def run_silver_transformation(conn):
    print("\n--- 2. Transformação da Camada Silver (SIST_CDB) ---")
    cur = conn.cursor()

    # 2.1 Silver Posição
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cdb.silver_posicao (
            id_posicao VARCHAR(100) PRIMARY KEY,
            dt_posicao DATE NOT NULL,
            cd_certificado VARCHAR(100) NOT NULL,
            id_cliente VARCHAR(100) NOT NULL,
            cd_tipo_cdb VARCHAR(50) NOT NULL,
            vl_principal_aplicado NUMERIC(18,2) NOT NULL,
            vl_saldo_bruto NUMERIC(18,2) NOT NULL,
            vl_saldo_liquido NUMERIC(18,2) NOT NULL,
            tx_remuneracao NUMERIC(8,4) NOT NULL,
            dt_aplicacao DATE NOT NULL,
            dt_vencimento DATE NOT NULL,
            dh_ingestao_utc TIMESTAMP NOT NULL
        );
    """)

    cur.execute("""
        INSERT INTO cdb.silver_posicao
        SELECT DISTINCT ON (id_posicao)
            id_posicao, dt_posicao, cd_certificado, id_cliente, cd_tipo_cdb,
            vl_principal_aplicado, vl_saldo_bruto, vl_saldo_liquido, tx_remuneracao,
            dt_aplicacao, dt_vencimento, dh_ingestao_utc
        FROM cdb.bronze_posicao
        ON CONFLICT (id_posicao) DO UPDATE SET
            vl_saldo_bruto = EXCLUDED.vl_saldo_bruto,
            vl_saldo_liquido = EXCLUDED.vl_saldo_liquido,
            dh_ingestao_utc = EXCLUDED.dh_ingestao_utc;
    """)

    # 2.2 Silver Movimentação
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cdb.silver_movimentacao (
            id_movimentacao VARCHAR(100) PRIMARY KEY,
            dt_movimentacao DATE NOT NULL,
            cd_certificado VARCHAR(100) NOT NULL,
            id_cliente VARCHAR(100) NOT NULL,
            tp_movimentacao VARCHAR(50) NOT NULL,
            vl_movimentacao NUMERIC(18,2) NOT NULL,
            vl_iof NUMERIC(18,2) NOT NULL,
            vl_ir NUMERIC(18,2) NOT NULL,
            vl_liquido_movimentado NUMERIC(18,2) NOT NULL,
            dh_liquidacao_utc TIMESTAMP NOT NULL
        );
    """)

    cur.execute("""
        INSERT INTO cdb.silver_movimentacao
        SELECT DISTINCT ON (id_movimentacao)
            id_movimentacao, dt_movimentacao, cd_certificado, id_cliente,
            tp_movimentacao, vl_movimentacao, vl_iof, vl_ir,
            vl_liquido_movimentado, dh_liquidacao_utc
        FROM cdb.bronze_movimentacao
        ON CONFLICT (id_movimentacao) DO NOTHING;
    """)

    cur.execute("SELECT COUNT(*) FROM cdb.silver_posicao;")
    c_pos = cur.fetchone()[0]
    print(f">>> [SIST_CDB] Silver concluída! Registros na silver_posicao: {c_pos}")

def run_quality_checks_and_observability(conn):
    print("\n--- 3. Execução dos Testes de Qualidade ODCS & Observabilidade ---")
    cur = conn.cursor()

    # Teste 1: check_saldo_positivo
    cur.execute("SELECT COUNT(*) FROM cdb.silver_posicao WHERE vl_saldo_bruto < 0 OR vl_saldo_liquido < 0;")
    violations = cur.fetchone()[0]
    passed = (violations == 0)
    msg = f"0 violações encontradas" if passed else f"{violations} posições com saldo negativo!"
    publish_test_result_to_om("check_saldo_positivo", "investments.cdb.silver_posicao", passed, msg, violations)

    # Teste 2: check_consistencia_liquido_bruto
    cur.execute("SELECT COUNT(*) FROM cdb.silver_posicao WHERE vl_saldo_liquido > vl_saldo_bruto;")
    violations = cur.fetchone()[0]
    passed = (violations == 0)
    msg = f"Consistência OK (líquido <= bruto)" if passed else f"{violations} posições com saldo líquido maior que bruto!"
    publish_test_result_to_om("check_consistencia_liquido_bruto", "investments.cdb.silver_posicao", passed, msg, violations)

    # Teste 3: check_vencimento_posterior_aplicacao
    cur.execute("SELECT COUNT(*) FROM cdb.silver_posicao WHERE dt_vencimento < dt_aplicacao;")
    violations = cur.fetchone()[0]
    passed = (violations == 0)
    msg = f"Validação temporal OK (vencimento >= aplicação)" if passed else f"{violations} certificados com datas invertidas!"
    publish_test_result_to_om("check_vencimento_posterior_aplicacao", "investments.cdb.silver_posicao", passed, msg, violations)

    # Teste 4: check_valor_movimentacao_positivo
    cur.execute("SELECT COUNT(*) FROM cdb.silver_movimentacao WHERE vl_movimentacao <= 0;")
    violations = cur.fetchone()[0]
    passed = (violations == 0)
    msg = f"Movimentações com valores estritamente positivos" if passed else f"{violations} lançamentos com valor zerado/negativo!"
    publish_test_result_to_om("check_valor_movimentacao_positivo", "investments.cdb.silver_movimentacao", passed, msg, violations)

def main():
    print("=" * 65)
    print("EXECUTANDO PIPELINE K3S: SIST_CDB")
    print("=" * 65)
    conn = get_connection()
    try:
        run_bronze_ingestion(conn)
        run_silver_transformation(conn)
        run_quality_checks_and_observability(conn)
        print("\n" + "=" * 65)
        print("PIPELINE SIST_CDB FINALIZADO COM SUCESSO!")
        print("=" * 65)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
