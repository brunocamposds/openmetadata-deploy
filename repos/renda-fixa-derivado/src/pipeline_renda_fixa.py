"""
Pipeline Consolidado RENDA_FIXA_DERIVADO (Job Kubernetes)
Execução: Cluster K3s via ClickHouse Server, MongoDB Pod & OpenMetadata API
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
import pymongo
import requests
from datetime import datetime, timezone
import clickhouse_connect

# Configurações do ambiente K3s
CH_HOST = os.getenv("CLICKHOUSE_SERVER_HOST", "clickhouse-server.openmetadata.svc.cluster.local")
CH_PORT = int(os.getenv("CLICKHOUSE_SERVER_PORT", "8123"))
CH_DB = os.getenv("CLICKHOUSE_DB", "investments")
CH_USER = os.getenv("CLICKHOUSE_USER", "clickhouse_user")
CH_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "clickhouse_password")

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://mongodb.openmetadata.svc.cluster.local:27017")
OM_URL = os.getenv("OPENMETADATA_URL", "http://openmetadata.openmetadata.svc.cluster.local:8585/api")
OM_USER = os.getenv("OPENMETADATA_ADMIN_EMAIL", "admin@open-metadata.org")
OM_PASSWORD = os.getenv("OPENMETADATA_ADMIN_PASSWORD", "admin")

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

def get_clickhouse_client():
    print(f">>> [RENDA_FIXA] Conectando ao ClickHouse Server em {CH_HOST}:{CH_PORT}...")
    for host, port in [(CH_HOST, CH_PORT), ("localhost", 8123)]:
        try:
            client = clickhouse_connect.get_client(host=host, port=port, username=CH_USER, password=CH_PASSWORD)
            return client
        except Exception:
            continue
    return clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)

def get_mongo_collection():
    print(f">>> [RENDA_FIXA] Conectando ao MongoDB Serving Store em {MONGO_URI}...")
    for uri in [MONGO_URI, "mongodb://localhost:27017"]:
        try:
            client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=2000)
            client.admin.command('ping')
            db = client["investments_serving"]
            return db["rf_customer_positions"]
        except Exception:
            continue
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
    elif not table_fqn.startswith("clickhouse_server."):
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

def run_silver_consolidation(client):
    print("\n--- 1. Consolidação da Camada Silver (RENDA_FIXA_DERIVADO) ---")
    client.command("CREATE DATABASE IF NOT EXISTS renda_fixa;")

    # 1.1 Tabela Silver Posição Consolidada
    client.command("""
        CREATE TABLE IF NOT EXISTS renda_fixa.silver_posicao (
            id_posicao_unificada String,
            dt_posicao Date,
            id_cliente String,
            tp_produto_renda_fixa String,
            cd_instrumento String,
            vl_principal_aplicado Decimal(18,2),
            vl_saldo_bruto Decimal(18,2),
            vl_saldo_liquido Decimal(18,2),
            dt_vencimento Date
        ) ENGINE = ReplacingMergeTree()
        ORDER BY id_posicao_unificada;
    """)

    client.command("TRUNCATE TABLE renda_fixa.silver_posicao;")

    # Mapeamento e unificação de CDB
    client.command("""
        INSERT INTO renda_fixa.silver_posicao
        SELECT 
            hex(MD5(concat('CDB||', id_posicao))) AS id_posicao_unificada,
            dt_posicao,
            id_cliente,
            'CDB' AS tp_produto_renda_fixa,
            cd_certificado AS cd_instrumento,
            vl_principal_aplicado,
            vl_saldo_bruto,
            vl_saldo_liquido,
            dt_vencimento
        FROM cdb.silver_posicao;
    """)

    # Mapeamento e unificação de CRA
    client.command("""
        INSERT INTO renda_fixa.silver_posicao
        SELECT 
            hex(MD5(concat('CRA||', id_posicao))) AS id_posicao_unificada,
            dt_posicao,
            id_cliente,
            'CRA' AS tp_produto_renda_fixa,
            cd_cra_isin AS cd_instrumento,
            vl_principal_aplicado,
            vl_saldo_bruto,
            vl_saldo_liquido,
            dt_vencimento
        FROM cra.silver_posicao;
    """)

    # 1.2 Tabela Silver Movimentação Consolidada
    client.command("""
        CREATE TABLE IF NOT EXISTS renda_fixa.silver_movimentacao (
            id_movimentacao_unificada String,
            dt_movimentacao Date,
            id_cliente String,
            tp_produto String,
            cd_instrumento String,
            tp_movimentacao String,
            vl_movimentado Decimal(18,2),
            dh_processamento_utc DateTime
        ) ENGINE = ReplacingMergeTree()
        ORDER BY id_movimentacao_unificada;
    """)

    client.command("TRUNCATE TABLE renda_fixa.silver_movimentacao;")

    client.command("""
        INSERT INTO renda_fixa.silver_movimentacao
        SELECT 
            hex(MD5(concat('CDB||', id_movimentacao))) AS id_movimentacao_unificada,
            dt_movimentacao, id_cliente, 'CDB' AS tp_produto, cd_certificado AS cd_instrumento,
            tp_movimentacao, vl_movimentacao AS vl_movimentado, dh_liquidacao_utc AS dh_processamento_utc
        FROM cdb.silver_movimentacao;
    """)

    client.command("""
        INSERT INTO renda_fixa.silver_movimentacao
        SELECT 
            hex(MD5(concat('CRA||', id_movimentacao))) AS id_movimentacao_unificada,
            dt_movimentacao, id_cliente, 'CRA' AS tp_produto, cd_cra_isin AS cd_instrumento,
            tp_movimentacao, vl_financeiro_movimentado AS vl_movimentado, dh_processamento_utc
        FROM cra.silver_movimentacao;
    """)

    c_pos = client.query("SELECT count() FROM renda_fixa.silver_posicao").result_rows[0][0]
    print(f">>> [RENDA_FIXA] Silver consolidada com sucesso! Total de posições ativas: {c_pos}")

def run_gold_aggregation(client):
    print("\n--- 2. Agregação e Métricas da Camada Gold ---")

    # 2.1 Gold Saldo Investido
    client.command("""
        CREATE TABLE IF NOT EXISTS renda_fixa.gold_saldo_investido (
            id_cliente String,
            dt_posicao Date,
            vl_total_aplicado_instituicao Decimal(18,2),
            vl_total_bruto_instituicao Decimal(18,2),
            vl_total_liquido_instituicao Decimal(18,2),
            qt_titulos_ativos UInt32
        ) ENGINE = ReplacingMergeTree()
        ORDER BY (id_cliente, dt_posicao);
    """)

    client.command("TRUNCATE TABLE renda_fixa.gold_saldo_investido;")

    client.command("""
        INSERT INTO renda_fixa.gold_saldo_investido
        SELECT 
            id_cliente,
            dt_posicao,
            sum(vl_principal_aplicado) AS vl_total_aplicado_instituicao,
            sum(vl_saldo_bruto) AS vl_total_bruto_instituicao,
            sum(vl_saldo_liquido) AS vl_total_liquido_instituicao,
            count(DISTINCT cd_instrumento) AS qt_titulos_ativos
        FROM renda_fixa.silver_posicao
        GROUP BY id_cliente, dt_posicao;
    """)

    # 2.2 Gold Movimentação Sumarizada
    client.command("""
        CREATE TABLE IF NOT EXISTS renda_fixa.gold_movimentacao_sumarizada (
            id_cliente String,
            dt_referencia Date,
            vl_total_aportes Decimal(18,2),
            vl_total_resgates Decimal(18,2),
            vl_liquido_movimentado_dia Decimal(18,2)
        ) ENGINE = ReplacingMergeTree()
        ORDER BY (id_cliente, dt_referencia);
    """)

    client.command("TRUNCATE TABLE renda_fixa.gold_movimentacao_sumarizada;")

    client.command("""
        INSERT INTO renda_fixa.gold_movimentacao_sumarizada
        SELECT 
            id_cliente,
            dt_movimentacao AS dt_referencia,
            sum(if(tp_movimentacao IN ('APORTE', 'SUBSCRIÇÃO'), vl_movimentado, 0)) AS vl_total_aportes,
            sum(if(position(tp_movimentacao, 'RESGATE') > 0, vl_movimentado, 0)) AS vl_total_resgates,
            sum(if(tp_movimentacao IN ('APORTE', 'SUBSCRIÇÃO'), vl_movimentado, -vl_movimentado)) AS vl_liquido_movimentado_dia
        FROM renda_fixa.silver_movimentacao
        GROUP BY id_cliente, dt_movimentacao;
    """)

    c_gold = client.query("SELECT count() FROM renda_fixa.gold_saldo_investido").result_rows[0][0]
    print(f">>> [RENDA_FIXA] Gold sumarizada com sucesso! Clientes com patrimônio: {c_gold}")

def run_quality_checks_and_observability(client):
    print("\n--- 3. Execução dos Testes de Qualidade ODCS & Observabilidade Gold ---")

    # Teste 1: check_saldo_gold_consistente
    violations = client.query("SELECT count() FROM renda_fixa.gold_saldo_investido WHERE vl_total_liquido_instituicao > vl_total_bruto_instituicao").result_rows[0][0]
    passed = (violations == 0)
    msg = f"Consistência patrimonial OK (Líquido total <= Bruto total)" if passed else f"{violations} clientes com inconsistência!"
    publish_test_result_to_om("check_saldo_gold_consistente", "clickhouse_server.investments.renda_fixa.gold_saldo_investido", passed, msg, violations)

    # Teste 2: check_qt_titulos_positiva
    violations = client.query("SELECT count() FROM renda_fixa.gold_saldo_investido WHERE qt_titulos_ativos <= 0").result_rows[0][0]
    passed = (violations == 0)
    msg = f"Contagem de títulos ativos em carteira válida" if passed else f"{violations} registros inválidos!"
    publish_test_result_to_om("check_qt_titulos_positiva", "clickhouse_server.investments.renda_fixa.gold_saldo_investido", passed, msg, violations)

def export_to_mongodb_serving(client):
    print("\n--- 4. Exportação Operacional para MongoDB Serving Layer ---")
    mongo_col = get_mongo_collection()

    clients_data = client.query("""
        SELECT id_cliente, dt_posicao, vl_total_aplicado_instituicao, vl_total_bruto_instituicao, vl_total_liquido_instituicao
        FROM renda_fixa.gold_saldo_investido
    """).result_rows

    inserted_count = 0
    now_utc = datetime.now(timezone.utc)

    for client_row in clients_data:
        id_cli, dt_pos, total_app, total_bruto, total_liq = client_row

        products = client.query(f"""
            SELECT tp_produto_renda_fixa, cd_instrumento, vl_principal_aplicado, vl_saldo_bruto, vl_saldo_liquido, dt_vencimento
            FROM renda_fixa.silver_posicao
            WHERE id_cliente = '{id_cli}' AND dt_posicao = '{dt_pos}'
        """).result_rows

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
    print("EXECUTANDO PIPELINE K3S: RENDA_FIXA_DERIVADO (ClickHouse)")
    print("=" * 65)
    client = get_clickhouse_client()
    try:
        run_silver_consolidation(client)
        run_gold_aggregation(client)
        run_quality_checks_and_observability(client)
        export_to_mongodb_serving(client)
        print("\n" + "=" * 65)
        print("PIPELINE RENDA_FIXA_DERIVADO FINALIZADO COM SUCESSO!")
        print("=" * 65)
    finally:
        client.close()

if __name__ == "__main__":
    main()
