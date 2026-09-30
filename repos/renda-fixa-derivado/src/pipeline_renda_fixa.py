"""
Pipeline Consolidado RENDA_FIXA_DERIVADO (Job Kubernetes)
Execução: Cluster K3s via DuckDB Server, MongoDB Pod & OpenMetadata API
Fluxo:
  1. Consolidação Silver (CDB + CRA -> renda_fixa.silver_posicao e silver_movimentacao)
  2. Métricas Analíticas Gold (renda_fixa.gold_saldo_investido e gold_movimentacao_sumarizada)
  3. Validação de Qualidade ODCS
  4. Serving Layer: Exportação de Documentos BSON para MongoDB (investments_serving.rf_customer_positions)
  5. Publicação de Métricas e Testes no OpenMetadata
"""

import os
import sys
import time
import base64
import hashlib
import psycopg2
import pymongo
import requests
from datetime import datetime, timezone

# Configurações do ambiente K3s
DB_HOST = os.getenv("DUCKDB_SERVER_HOST", "duckdb-server.openmetadata.svc.cluster.local")
DB_PORT = int(os.getenv("DUCKDB_SERVER_PORT", "5433"))
DB_NAME = os.getenv("DUCKDB_DB", "investments")
DB_USER = os.getenv("DUCKDB_USER", "duckdb_user")
DB_PASSWORD = os.getenv("DUCKDB_PASSWORD", "duckdb_password")
MONGO_URI = os.getenv("MONGODB_URI", "mongodb://mongodb.openmetadata.svc.cluster.local:27017")
OM_URL = os.getenv("OPENMETADATA_URL", "http://openmetadata.openmetadata.svc.cluster.local:8585/api")
OM_USER = os.getenv("OPENMETADATA_ADMIN_EMAIL", "admin@open-metadata.org")
OM_PASSWORD = os.getenv("OPENMETADATA_ADMIN_PASSWORD", "admin")

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

def get_duckdb_conn():
    print(f">>> [RENDA_FIXA] Conectando ao DuckDB Server em {DB_HOST}:{DB_PORT}/{DB_NAME}...")
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    conn.autocommit = True
    return conn

def get_mongo_collection():
    print(f">>> [RENDA_FIXA] Conectando ao MongoDB Serving Store em {MONGO_URI}...")
    client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client["investments_serving"]
    return db["rf_customer_positions"]

def publish_test_result_to_om(test_name: str, table_fqn: str, passed: bool, message: str, row_count: int):
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    status_str = "Success" if passed else "Failed"
    print(f">>> [OM Observability] Reportando teste '{test_name}' para {table_fqn}: {status_str} ({message})")

    if "mongodb" in table_fqn or "investments_serving" in table_fqn:
        if not table_fqn.startswith("mongodb_k3s."):
            full_table_fqn = f"mongodb_k3s.investments_serving.collections.{table_fqn.split('.')[-1]}"
        else:
            full_table_fqn = table_fqn
    elif not table_fqn.startswith("duckdb_server."):
        full_table_fqn = f"duckdb_server.{table_fqn}"
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

def run_silver_consolidation(conn):
    print("\n--- 1. Consolidação da Camada Silver (RENDA_FIXA_DERIVADO) ---")
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS renda_fixa;")

    # 1.1 Tabela Silver Posição Consolidada
    cur.execute("""
        CREATE TABLE IF NOT EXISTS renda_fixa.silver_posicao (
            id_posicao_unificada VARCHAR(100) PRIMARY KEY,
            dt_posicao DATE NOT NULL,
            id_cliente VARCHAR(100) NOT NULL,
            tp_produto_renda_fixa VARCHAR(20) NOT NULL,
            cd_instrumento VARCHAR(100) NOT NULL,
            vl_principal_aplicado NUMERIC(18,2) NOT NULL,
            vl_saldo_bruto NUMERIC(18,2) NOT NULL,
            vl_saldo_liquido NUMERIC(18,2) NOT NULL,
            dt_vencimento DATE NOT NULL
        );
    """)

    # Mapeamento e unificação de CDB
    cur.execute("""
        INSERT INTO renda_fixa.silver_posicao
        SELECT 
            md5('CDB||' || id_posicao) AS id_posicao_unificada,
            dt_posicao,
            id_cliente,
            'CDB' AS tp_produto_renda_fixa,
            cd_certificado AS cd_instrumento,
            vl_principal_aplicado,
            vl_saldo_bruto,
            vl_saldo_liquido,
            dt_vencimento
        FROM cdb.silver_posicao
        ON CONFLICT (id_posicao_unificada) DO UPDATE SET
            vl_saldo_bruto = EXCLUDED.vl_saldo_bruto,
            vl_saldo_liquido = EXCLUDED.vl_saldo_liquido;
    """)

    # Mapeamento e unificação de CRA
    cur.execute("""
        INSERT INTO renda_fixa.silver_posicao
        SELECT 
            md5('CRA||' || id_posicao) AS id_posicao_unificada,
            dt_posicao,
            id_cliente,
            'CRA' AS tp_produto_renda_fixa,
            cd_cra_isin AS cd_instrumento,
            vl_principal_aplicado,
            vl_saldo_bruto,
            vl_saldo_liquido,
            dt_vencimento
        FROM cra.silver_posicao
        ON CONFLICT (id_posicao_unificada) DO UPDATE SET
            vl_saldo_bruto = EXCLUDED.vl_saldo_bruto,
            vl_saldo_liquido = EXCLUDED.vl_saldo_liquido;
    """)

    # 1.2 Tabela Silver Movimentação Consolidada
    cur.execute("""
        CREATE TABLE IF NOT EXISTS renda_fixa.silver_movimentacao (
            id_movimentacao_unificada VARCHAR(100) PRIMARY KEY,
            dt_movimentacao DATE NOT NULL,
            id_cliente VARCHAR(100) NOT NULL,
            tp_produto VARCHAR(20) NOT NULL,
            cd_instrumento VARCHAR(100) NOT NULL,
            tp_movimentacao VARCHAR(50) NOT NULL,
            vl_movimentado NUMERIC(18,2) NOT NULL,
            dh_processamento_utc TIMESTAMP NOT NULL
        );
    """)

    cur.execute("""
        INSERT INTO renda_fixa.silver_movimentacao
        SELECT 
            md5('CDB||' || id_movimentacao) AS id_movimentacao_unificada,
            dt_movimentacao, id_cliente, 'CDB' AS tp_produto, cd_certificado AS cd_instrumento,
            tp_movimentacao, vl_movimentacao AS vl_movimentado, dh_liquidacao_utc AS dh_processamento_utc
        FROM cdb.silver_movimentacao
        ON CONFLICT (id_movimentacao_unificada) DO NOTHING;
    """)

    cur.execute("""
        INSERT INTO renda_fixa.silver_movimentacao
        SELECT 
            md5('CRA||' || id_movimentacao) AS id_movimentacao_unificada,
            dt_movimentacao, id_cliente, 'CRA' AS tp_produto, cd_cra_isin AS cd_instrumento,
            tp_movimentacao, vl_financeiro_movimentado AS vl_movimentado, dh_processamento_utc
        FROM cra.silver_movimentacao
        ON CONFLICT (id_movimentacao_unificada) DO NOTHING;
    """)

    cur.execute("SELECT COUNT(*) FROM renda_fixa.silver_posicao;")
    c_pos = cur.fetchone()[0]
    print(f">>> [RENDA_FIXA] Silver consolidada com sucesso! Total de posições ativas: {c_pos}")

def run_gold_aggregation(conn):
    print("\n--- 2. Agregação e Métricas da Camada Gold ---")
    cur = conn.cursor()

    # 2.1 Gold Saldo Investido
    cur.execute("""
        CREATE TABLE IF NOT EXISTS renda_fixa.gold_saldo_investido (
            id_cliente VARCHAR(100) NOT NULL,
            dt_posicao DATE NOT NULL,
            vl_total_aplicado_instituicao NUMERIC(18,2) NOT NULL,
            vl_total_bruto_instituicao NUMERIC(18,2) NOT NULL,
            vl_total_liquido_instituicao NUMERIC(18,2) NOT NULL,
            qt_titulos_ativos INT NOT NULL,
            PRIMARY KEY (id_cliente, dt_posicao)
        );
    """)

    cur.execute("""
        INSERT INTO renda_fixa.gold_saldo_investido
        SELECT 
            id_cliente,
            dt_posicao,
            SUM(vl_principal_aplicado) AS vl_total_aplicado_instituicao,
            SUM(vl_saldo_bruto) AS vl_total_bruto_instituicao,
            SUM(vl_saldo_liquido) AS vl_total_liquido_instituicao,
            COUNT(DISTINCT cd_instrumento) AS qt_titulos_ativos
        FROM renda_fixa.silver_posicao
        GROUP BY id_cliente, dt_posicao
        ON CONFLICT (id_cliente, dt_posicao) DO UPDATE SET
            vl_total_aplicado_instituicao = EXCLUDED.vl_total_aplicado_instituicao,
            vl_total_bruto_instituicao = EXCLUDED.vl_total_bruto_instituicao,
            vl_total_liquido_instituicao = EXCLUDED.vl_total_liquido_instituicao,
            qt_titulos_ativos = EXCLUDED.qt_titulos_ativos;
    """)

    # 2.2 Gold Movimentação Sumarizada
    cur.execute("""
        CREATE TABLE IF NOT EXISTS renda_fixa.gold_movimentacao_sumarizada (
            id_cliente VARCHAR(100) NOT NULL,
            dt_referencia DATE NOT NULL,
            vl_total_aportes NUMERIC(18,2) NOT NULL,
            vl_total_resgates NUMERIC(18,2) NOT NULL,
            vl_liquido_movimentado_dia NUMERIC(18,2) NOT NULL,
            PRIMARY KEY (id_cliente, dt_referencia)
        );
    """)

    cur.execute("""
        INSERT INTO renda_fixa.gold_movimentacao_sumarizada
        SELECT 
            id_cliente,
            dt_movimentacao AS dt_referencia,
            COALESCE(SUM(CASE WHEN tp_movimentacao IN ('APORTE', 'SUBSCRIÇÃO') THEN vl_movimentado ELSE 0 END), 0) AS vl_total_aportes,
            COALESCE(SUM(CASE WHEN tp_movimentacao LIKE '%RESGATE%' THEN vl_movimentado ELSE 0 END), 0) AS vl_total_resgates,
            COALESCE(SUM(CASE WHEN tp_movimentacao IN ('APORTE', 'SUBSCRIÇÃO') THEN vl_movimentado ELSE -vl_movimentado END), 0) AS vl_liquido_movimentado_dia
        FROM renda_fixa.silver_movimentacao
        GROUP BY id_cliente, dt_movimentacao
        ON CONFLICT (id_cliente, dt_referencia) DO UPDATE SET
            vl_total_aportes = EXCLUDED.vl_total_aportes,
            vl_total_resgates = EXCLUDED.vl_total_resgates,
            vl_liquido_movimentado_dia = EXCLUDED.vl_liquido_movimentado_dia;
    """)

    cur.execute("SELECT COUNT(*) FROM renda_fixa.gold_saldo_investido;")
    c_gold = cur.fetchone()[0]
    print(f">>> [RENDA_FIXA] Gold sumarizada com sucesso! Clientes com patrimônio: {c_gold}")

def run_quality_checks_and_observability(conn):
    print("\n--- 3. Execução dos Testes de Qualidade ODCS & Observabilidade Gold ---")
    cur = conn.cursor()

    # Teste 1: check_saldo_gold_consistente
    cur.execute("SELECT COUNT(*) FROM renda_fixa.gold_saldo_investido WHERE vl_total_liquido_instituicao > vl_total_bruto_instituicao;")
    violations = cur.fetchone()[0]
    passed = (violations == 0)
    msg = f"Consistência patrimonial OK (Líquido total <= Bruto total)" if passed else f"{violations} clientes com inconsistência!"
    publish_test_result_to_om("check_saldo_gold_consistente", "investments.renda_fixa.gold_saldo_investido", passed, msg, violations)

    # Teste 2: check_qt_titulos_positiva
    cur.execute("SELECT COUNT(*) FROM renda_fixa.gold_saldo_investido WHERE qt_titulos_ativos <= 0;")
    violations = cur.fetchone()[0]
    passed = (violations == 0)
    msg = f"Contagem de títulos ativos em carteira válida" if passed else f"{violations} registros inválidos!"
    publish_test_result_to_om("check_qt_titulos_positiva", "investments.renda_fixa.gold_saldo_investido", passed, msg, violations)

def export_to_mongodb_serving(conn):
    print("\n--- 4. Exportação Operacional para MongoDB Serving Layer ---")
    mongo_col = get_mongo_collection()
    cur = conn.cursor()

    # Consulta dos clientes na Gold
    cur.execute("""
        SELECT id_cliente, dt_posicao, vl_total_aplicado_instituicao, vl_total_bruto_instituicao, vl_total_liquido_instituicao
        FROM renda_fixa.gold_saldo_investido;
    """)
    clients = cur.fetchall()

    inserted_count = 0
    now_utc = datetime.now(timezone.utc)

    for client_row in clients:
        id_cli, dt_pos, total_app, total_bruto, total_liq = client_row

        # Consulta lista aninhada de títulos ativos do cliente
        cur.execute("""
            SELECT tp_produto_renda_fixa, cd_instrumento, vl_principal_aplicado, vl_saldo_bruto, vl_saldo_liquido, dt_vencimento
            FROM renda_fixa.silver_posicao
            WHERE id_cliente = %s AND dt_posicao = %s;
        """, (id_cli, dt_pos))
        products = cur.fetchall()

        products_summary = []
        for p in products:
            products_summary.append({
                "productType": p[0],
                "instrumentCode": p[1],
                "appliedValue": float(p[2]),
                "grossBalance": float(p[3]),
                "netBalance": float(p[4]),
                "dueDate": str(p[5])
            })

        # Montagem do documento de acordo com o contrato ODCS rf-mongo-canal.odcs.yaml
        doc = {
            "_id": id_cli,
            "customerId": id_cli,
            "snapshotDate": str(dt_pos),
            "totalInvested": float(total_app),
            "totalGrossBalance": float(total_bruto),
            "totalNetBalance": float(total_liq),
            "productsSummary": products_summary,
            "lastUpdatedUtc": now_utc
        }

        # Upsert baseado na chave única do cliente
        mongo_col.replace_one({"_id": id_cli}, doc, upsert=True)
        inserted_count += 1

    print(f">>> [RENDA_FIXA] Sincronização MongoDB concluída! Documentos upsertados em investments_serving.rf_customer_positions: {inserted_count}")

    # Teste de qualidade no Mongo
    invalid_docs = mongo_col.count_documents({"$expr": {"$gt": ["$totalNetBalance", "$totalGrossBalance"]}})
    passed = (invalid_docs == 0)
    msg = f"Documentos do MongoDB consistentes com o contrato ODCS" if passed else f"{invalid_docs} documentos violando contrato!"
    publish_test_result_to_om("check_balances_valid", "investments_serving.rf_customer_positions", passed, msg, invalid_docs)

def main():
    print("=" * 65)
    print("EXECUTANDO PIPELINE K3S: RENDA_FIXA_DERIVADO")
    print("=" * 65)
    conn = get_duckdb_conn()
    try:
        run_silver_consolidation(conn)
        run_gold_aggregation(conn)
        run_quality_checks_and_observability(conn)
        export_to_mongodb_serving(conn)
        print("\n" + "=" * 65)
        print("PIPELINE RENDA_FIXA_DERIVADO FINALIZADO COM SUCESSO!")
        print("=" * 65)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
