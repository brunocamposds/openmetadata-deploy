"""
Pipeline Completo SIST_CDB (Job Kubernetes)
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
    print(f">>> [SIST_CDB] Conectando ao ClickHouse Server em {CH_HOST}:{CH_PORT}...")
    for host, port in [(CH_HOST, CH_PORT), ("localhost", 8123)]:
        try:
            client = clickhouse_connect.get_client(host=host, port=port, username=CH_USER, password=CH_PASSWORD)
            return client
        except Exception:
            continue
    # Tentativa final direta
    return clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)

def publish_test_result_to_om(test_name: str, table_fqn: str, passed: bool, message: str, row_count: int):
    """Envia resultado do teste para a API do OpenMetadata para observabilidade e alertas."""
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    status_str = "Success" if passed else "Failed"
    print(f">>> [OM Observability] Reportando teste '{test_name}' para {table_fqn}: {status_str} ({message})")

    # Garante prefixo clickhouse_server se não informado
    if not table_fqn.startswith("clickhouse_server.") and not table_fqn.startswith("mongodb_k3s."):
        full_table_fqn = f"clickhouse_server.{table_fqn}"
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

    # 3. Se o teste falhou, acionar Incidente e notificação no Sininho / Activity Feed
    if not passed:
        try:
            # 3.1 Abrir Incidente de Severidade 1 atribuído ao Admin
            inc_payload = {
                "testCaseReference": f"<#E::testCase::{tc_fqn}>",
                "testCaseResolutionStatusType": "New",
                "severity": "Severity1",
                "testCaseResolutionStatusDetails": {
                    "assignee": {
                        "name": "admin",
                        "type": "user"
                    }
                }
            }
            requests.post(f"{OM_URL.rstrip('/')}/v1/dataQuality/testCases/testCaseIncidentStatus", headers=headers, json=inc_payload, timeout=30)
        except Exception:
            pass

        try:
            # 3.2 Notificar no feed interno endereçado ao admin para acender o sininho (Notifications)
            feed_payload = {
                "about": f"<#E::table::{full_table_fqn}>",
                "addressedTo": "<#E::user::admin>",
                "message": f"<#E::user::admin> :rotating_light: **ALERTA CRÍTICO DE OBSERVABILIDADE [SIST_CDB]**: Violação de integridade no contrato ODCS da tabela `{table_fqn}`! O teste `{test_name}` falhou. Detalhes: {message}",
                "type": "Conversation"
            }
            feed_res = requests.post(f"{OM_URL.rstrip('/')}/v1/feed", headers=headers, json=feed_payload, timeout=30)
            if feed_res.status_code in (200, 201):
                print(f"    [🔔 Sininho] Notificação de incidente gerada no feed do usuário admin!")
            else:
                print(f"    [Info feed] Status {feed_res.status_code}: {feed_res.text[:100]}")
        except Exception as fe:
            print(f"    [Aviso feed]: {fe}")

def run_bronze_ingestion(client):
    print("\n--- 1. Ingestão da Camada Bronze (SIST_CDB) ---")
    client.command("CREATE DATABASE IF NOT EXISTS cdb;")

    pos_seed = SEEDS_DIR / "cdb_posicao_seed.csv"
    mov_seed = SEEDS_DIR / "cdb_movimentacao_seed.csv"

    # 1.1 Bronze Posição
    client.command("""
        CREATE TABLE IF NOT EXISTS cdb.bronze_posicao (
            id_posicao String,
            dt_posicao Date,
            cd_certificado String,
            id_cliente String,
            cd_tipo_cdb String,
            vl_principal_aplicado Decimal(18,2),
            vl_saldo_bruto Decimal(18,2),
            vl_saldo_liquido Decimal(18,2),
            tx_remuneracao Decimal(8,4),
            dt_aplicacao Date,
            dt_vencimento Date,
            dh_ingestao_utc DateTime,
            _raw_file String,
            _ingested_at DateTime DEFAULT now(),
            _source_system String DEFAULT 'SIST_CDB_ORACLE_CORE'
        ) ENGINE = MergeTree()
        ORDER BY id_posicao;
    """)

    client.command("TRUNCATE TABLE cdb.bronze_posicao;")

    # Leitura e inserção do CSV
    pos_rows = []
    with open(pos_seed, 'r', encoding='utf-8') as f:
        lines = f.readlines()[1:] # pula header
        for line in lines:
            parts = [p.strip() for p in line.strip().split(',')]
            if len(parts) >= 12:
                pos_rows.append([
                    parts[0], parse_date(parts[1]), parts[2], parts[3], parts[4],
                    float(parts[5]), float(parts[6]), float(parts[7]), float(parts[8]),
                    parse_date(parts[9]), parse_date(parts[10]), parse_datetime(parts[11]),
                    pos_seed.name
                ])

    if pos_rows:
        client.insert(
            "cdb.bronze_posicao",
            pos_rows,
            column_names=[
                "id_posicao", "dt_posicao", "cd_certificado", "id_cliente", "cd_tipo_cdb",
                "vl_principal_aplicado", "vl_saldo_bruto", "vl_saldo_liquido", "tx_remuneracao",
                "dt_aplicacao", "dt_vencimento", "dh_ingestao_utc", "_raw_file"
            ]
        )

    # 1.2 Bronze Movimentação
    client.command("""
        CREATE TABLE IF NOT EXISTS cdb.bronze_movimentacao (
            id_movimentacao String,
            dt_movimentacao Date,
            cd_certificado String,
            id_cliente String,
            tp_movimentacao String,
            vl_movimentacao Decimal(18,2),
            vl_iof Decimal(18,2),
            vl_ir Decimal(18,2),
            vl_liquido_movimentado Decimal(18,2),
            dh_liquidacao_utc DateTime,
            _raw_file String,
            _ingested_at DateTime DEFAULT now(),
            _source_system String DEFAULT 'SIST_CDB_ORACLE_CORE'
        ) ENGINE = MergeTree()
        ORDER BY id_movimentacao;
    """)

    client.command("TRUNCATE TABLE cdb.bronze_movimentacao;")

    mov_rows = []
    with open(mov_seed, 'r', encoding='utf-8') as f:
        lines = f.readlines()[1:]
        for line in lines:
            parts = [p.strip() for p in line.strip().split(',')]
            if len(parts) >= 10:
                mov_rows.append([
                    parts[0], parse_date(parts[1]), parts[2], parts[3], parts[4],
                    float(parts[5]), float(parts[6]), float(parts[7]), float(parts[8]),
                    parse_datetime(parts[9]),
                    mov_seed.name
                ])

    if mov_rows:
        client.insert(
            "cdb.bronze_movimentacao",
            mov_rows,
            column_names=[
                "id_movimentacao", "dt_movimentacao", "cd_certificado", "id_cliente",
                "tp_movimentacao", "vl_movimentacao", "vl_iof", "vl_ir",
                "vl_liquido_movimentado", "dh_liquidacao_utc", "_raw_file"
            ]
        )

    c_pos = client.query("SELECT count() FROM cdb.bronze_posicao").result_rows[0][0]
    c_mov = client.query("SELECT count() FROM cdb.bronze_movimentacao").result_rows[0][0]
    print(f">>> [SIST_CDB] Bronze concluída! Registros: {c_pos} posições, {c_mov} movimentações.")

def run_silver_transformation(client):
    print("\n--- 2. Transformação da Camada Silver (SIST_CDB) ---")

    # 2.1 Silver Posição
    client.command("""
        CREATE TABLE IF NOT EXISTS cdb.silver_posicao (
            id_posicao String,
            dt_posicao Date,
            cd_certificado String,
            id_cliente String,
            cd_tipo_cdb String,
            vl_principal_aplicado Decimal(18,2),
            vl_saldo_bruto Decimal(18,2),
            vl_saldo_liquido Decimal(18,2),
            tx_remuneracao Decimal(8,4),
            dt_aplicacao Date,
            dt_vencimento Date,
            dh_ingestao_utc DateTime
        ) ENGINE = ReplacingMergeTree()
        ORDER BY id_posicao;
    """)

    client.command("TRUNCATE TABLE cdb.silver_posicao;")

    client.command("""
        INSERT INTO cdb.silver_posicao
        SELECT
            id_posicao, dt_posicao, cd_certificado, id_cliente, cd_tipo_cdb,
            vl_principal_aplicado, vl_saldo_bruto, vl_saldo_liquido, tx_remuneracao,
            dt_aplicacao, dt_vencimento, dh_ingestao_utc
        FROM cdb.bronze_posicao;
    """)

    # 2.2 Silver Movimentação
    client.command("""
        CREATE TABLE IF NOT EXISTS cdb.silver_movimentacao (
            id_movimentacao String,
            dt_movimentacao Date,
            cd_certificado String,
            id_cliente String,
            tp_movimentacao String,
            vl_movimentacao Decimal(18,2),
            vl_iof Decimal(18,2),
            vl_ir Decimal(18,2),
            vl_liquido_movimentado Decimal(18,2),
            dh_liquidacao_utc DateTime
        ) ENGINE = ReplacingMergeTree()
        ORDER BY id_movimentacao;
    """)

    client.command("TRUNCATE TABLE cdb.silver_movimentacao;")

    client.command("""
        INSERT INTO cdb.silver_movimentacao
        SELECT
            id_movimentacao, dt_movimentacao, cd_certificado, id_cliente,
            tp_movimentacao, vl_movimentacao, vl_iof, vl_ir,
            vl_liquido_movimentado, dh_liquidacao_utc
        FROM cdb.bronze_movimentacao;
    """)

    # 2.3 Silver Certificado (Cadastro de Certificados - Tabela Solitária de Exemplo)
    cert_seed = SEEDS_DIR / "cdb_certificado_seed.csv"
    client.command("""
        CREATE TABLE IF NOT EXISTS cdb.silver_certificado (
            id_certificado Nullable(String),
            cd_tipo_certificado String,
            nm_emissor String,
            dt_emissao Date,
            dt_vencimento Date,
            tx_juros_anual Decimal(8,4),
            st_ativo UInt8,
            dh_registro_utc DateTime
        ) ENGINE = MergeTree()
        ORDER BY tuple();
    """)

    client.command("TRUNCATE TABLE cdb.silver_certificado;")
    if cert_seed.exists():
        cert_rows = []
        with open(cert_seed, 'r', encoding='utf-8') as f:
            lines = f.readlines()[1:]
            for line in lines:
                parts = [p.strip() for p in line.strip().split(',')]
                if len(parts) >= 8:
                    id_cert = parts[0] if parts[0] != '' else None
                    st_val = 1 if parts[6].lower() in ('true', '1') else 0
                    cert_rows.append([
                        id_cert, parts[1], parts[2], parse_date(parts[3]), parse_date(parts[4]),
                        float(parts[5]), st_val,
                        parse_datetime(parts[7])
                    ])
        if cert_rows:
            client.insert(
                "cdb.silver_certificado",
                cert_rows,
                column_names=[
                    "id_certificado", "cd_tipo_certificado", "nm_emissor",
                    "dt_emissao", "dt_vencimento", "tx_juros_anual",
                    "st_ativo", "dh_registro_utc"
                ]
            )

    c_pos = client.query("SELECT count() FROM cdb.silver_posicao").result_rows[0][0]
    c_cert = client.query("SELECT count() FROM cdb.silver_certificado").result_rows[0][0]
    print(f">>> [SIST_CDB] Silver concluída! Registros: {c_pos} posições, {c_cert} certificados cadastrados.")

def run_quality_checks_and_observability(client):
    print("\n--- 3. Execução dos Testes de Qualidade ODCS & Observabilidade ---")

    # Teste 1: check_saldo_positivo
    violations = client.query("SELECT count() FROM cdb.silver_posicao WHERE vl_saldo_bruto < 0 OR vl_saldo_liquido < 0").result_rows[0][0]
    passed = (violations == 0)
    msg = f"0 violações encontradas" if passed else f"{violations} posições com saldo negativo!"
    publish_test_result_to_om("check_saldo_positivo", "clickhouse_server.investments.cdb.silver_posicao", passed, msg, violations)

    # Teste 2: check_consistencia_liquido_bruto
    violations = client.query("SELECT count() FROM cdb.silver_posicao WHERE vl_saldo_liquido > vl_saldo_bruto").result_rows[0][0]
    passed = (violations == 0)
    msg = f"Consistência OK (líquido <= bruto)" if passed else f"{violations} posições com saldo líquido maior que bruto!"
    publish_test_result_to_om("check_consistencia_liquido_bruto", "clickhouse_server.investments.cdb.silver_posicao", passed, msg, violations)

    # Teste 3: check_vencimento_posterior_aplicacao
    violations = client.query("SELECT count() FROM cdb.silver_posicao WHERE dt_vencimento < dt_aplicacao").result_rows[0][0]
    passed = (violations == 0)
    msg = f"Validação temporal OK (vencimento >= aplicação)" if passed else f"{violations} certificados com datas invertidas!"
    publish_test_result_to_om("check_vencimento_posterior_aplicacao", "clickhouse_server.investments.cdb.silver_posicao", passed, msg, violations)

    # Teste 4: check_valor_movimentacao_positivo
    violations = client.query("SELECT count() FROM cdb.silver_movimentacao WHERE vl_movimentacao <= 0").result_rows[0][0]
    passed = (violations == 0)
    msg = f"Movimentações com valores estritamente positivos" if passed else f"{violations} lançamentos com valor zerado/negativo!"
    publish_test_result_to_om("check_valor_movimentacao_positivo", "clickhouse_server.investments.cdb.silver_movimentacao", passed, msg, violations)

    # Teste 5: check_id_certificado_not_null (ALERTA DE OBSERVABILIDADE - SIMULAÇÃO DE ANOMALIA)
    violations = client.query("SELECT count() FROM cdb.silver_certificado WHERE isNull(id_certificado) OR id_certificado = ''").result_rows[0][0]
    passed = (violations == 0)
    msg = f"0 violações encontradas" if passed else f"ALERTA CRÍTICO: {violations} certificado(s) com 'id_certificado' NULO/VAZIO violando o contrato ODCS!"
    publish_test_result_to_om("check_id_certificado_not_null", "clickhouse_server.investments.cdb.silver_certificado", passed, msg, violations)

    # Teste 6: check_dt_vencimento_valida
    violations = client.query("SELECT count() FROM cdb.silver_certificado WHERE dt_vencimento < dt_emissao").result_rows[0][0]
    passed = (violations == 0)
    msg = f"Vencimentos válidos (>= emissão)" if passed else f"{violations} certificados com vencimento anterior à emissão!"
    publish_test_result_to_om("check_dt_vencimento_valida", "clickhouse_server.investments.cdb.silver_certificado", passed, msg, violations)

    # Teste 7: check_taxa_positiva
    violations = client.query("SELECT count() FROM cdb.silver_certificado WHERE tx_juros_anual <= 0").result_rows[0][0]
    passed = (violations == 0)
    msg = f"Taxas de remuneração estritamente positivas" if passed else f"{violations} certificados com taxa zerada ou negativa!"
    publish_test_result_to_om("check_taxa_positiva", "clickhouse_server.investments.cdb.silver_certificado", passed, msg, violations)


def main():
    print("=" * 65)
    print("EXECUTANDO PIPELINE K3S: SIST_CDB (ClickHouse)")
    print("=" * 65)
    client = get_client()
    try:
        run_bronze_ingestion(client)
        run_silver_transformation(client)
        run_quality_checks_and_observability(client)
        print("\n" + "=" * 65)
        print("PIPELINE SIST_CDB FINALIZADO COM SUCESSO!")
        print("=" * 65)
    finally:
        client.close()

if __name__ == "__main__":
    main()
