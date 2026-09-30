"""
Pipeline de Ingestão Bronze - SIST_CDB
Engine: DuckDB + Apache Iceberg
Origem Declarada: SIST_CDB_ORACLE_CORE (mock via seeds CSV)
Descrição: Lê os arquivos seeds CSV de posição e movimentação de CDB,
           gera as tabelas na camada Bronze com armazenamento Iceberg
           e registra no catálogo do DuckDB em investments.duckdb.
"""

import os
import sys
import duckdb
from pathlib import Path

# Definição de diretórios relativos ao repositório
REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = REPO_ROOT.parent.parent
SEEDS_DIR = REPO_ROOT / "seeds"
DATA_DIR = PROJECT_ROOT / "data"
DUCKDB_PATH = DATA_DIR / "duckdb" / "investments.duckdb"
ICEBERG_BASE = DATA_DIR / "iceberg" / "cdb"

def get_duckdb_connection() -> duckdb.DuckDBPyConnection:
    """Abre conexão com o banco DuckDB compartilhado."""
    DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DUCKDB_PATH))
    # Carrega extensões úteis se disponíveis
    try:
        con.execute("INSTALL iceberg; LOAD iceberg;")
    except Exception:
        pass
    con.execute("CREATE SCHEMA IF NOT EXISTS cdb;")
    return con

def ingest_posicoes_bronze(con: duckdb.DuckDBPyConnection):
    seed_file = SEEDS_DIR / "cdb_posicao_seed.csv"
    if not seed_file.exists():
        raise FileNotFoundError(f"Seed não encontrado: {seed_file}")

    print(f">>> [SIST_CDB] Ingerindo posições brutas de: {seed_file.name}")
    
    # Cria tabela Bronze no DuckDB enriquecida com metadados de linhagem e origem
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS cdb.bronze_posicao AS 
        SELECT 
            *,
            '{seed_file.name}' AS _raw_file,
            CURRENT_TIMESTAMP AS _ingested_at,
            'SIST_CDB_ORACLE_CORE' AS _source_system
        FROM read_csv_auto('{seed_file.as_posix()}', header=True)
        WHERE 1=0;
    """)

    # Inserção incremental dos dados mock
    con.execute(f"""
        INSERT INTO cdb.bronze_posicao
        SELECT 
            *,
            '{seed_file.name}' AS _raw_file,
            CURRENT_TIMESTAMP AS _ingested_at,
            'SIST_CDB_ORACLE_CORE' AS _source_system
        FROM read_csv_auto('{seed_file.as_posix()}', header=True);
    """)

    # Exporta/persiste snapshot no formato Parquet/Iceberg
    iceberg_pos_dir = ICEBERG_BASE / "bronze_posicao"
    iceberg_pos_dir.mkdir(parents=True, exist_ok=True)
    parquet_target = iceberg_pos_dir / "data.parquet"
    con.execute(f"COPY cdb.bronze_posicao TO '{parquet_target.as_posix()}' (FORMAT PARQUET);")

    qtd = con.execute("SELECT count(*) FROM cdb.bronze_posicao").fetchone()[0]
    print(f">>> [SIST_CDB] cdb.bronze_posicao criada com sucesso! Total de registros: {qtd}")

def ingest_movimentacoes_bronze(con: duckdb.DuckDBPyConnection):
    seed_file = SEEDS_DIR / "cdb_movimentacao_seed.csv"
    if not seed_file.exists():
        raise FileNotFoundError(f"Seed não encontrado: {seed_file}")

    print(f">>> [SIST_CDB] Ingerindo movimentações brutas de: {seed_file.name}")

    con.execute(f"""
        CREATE TABLE IF NOT EXISTS cdb.bronze_movimentacao AS 
        SELECT 
            *,
            '{seed_file.name}' AS _raw_file,
            CURRENT_TIMESTAMP AS _ingested_at,
            'SIST_CDB_ORACLE_CORE' AS _source_system
        FROM read_csv_auto('{seed_file.as_posix()}', header=True)
        WHERE 1=0;
    """)

    con.execute(f"""
        INSERT INTO cdb.bronze_movimentacao
        SELECT 
            *,
            '{seed_file.name}' AS _raw_file,
            CURRENT_TIMESTAMP AS _ingested_at,
            'SIST_CDB_ORACLE_CORE' AS _source_system
        FROM read_csv_auto('{seed_file.as_posix()}', header=True);
    """)

    iceberg_mov_dir = ICEBERG_BASE / "bronze_movimentacao"
    iceberg_mov_dir.mkdir(parents=True, exist_ok=True)
    parquet_target = iceberg_mov_dir / "data.parquet"
    con.execute(f"COPY cdb.bronze_movimentacao TO '{parquet_target.as_posix()}' (FORMAT PARQUET);")

    qtd = con.execute("SELECT count(*) FROM cdb.bronze_movimentacao").fetchone()[0]
    print(f">>> [SIST_CDB] cdb.bronze_movimentacao criada com sucesso! Total de registros: {qtd}")

def main():
    print("=" * 60)
    print("INICIANDO INGESTÃO BRONZE: SIST_CDB (DuckDB + Iceberg)")
    print("=" * 60)
    con = get_duckdb_connection()
    try:
        ingest_posicoes_bronze(con)
        ingest_movimentacoes_bronze(con)
        print("=" * 60)
        print("INGESTÃO BRONZE SIST_CDB FINALIZADA COM SUCESSO!")
        print("=" * 60)
    finally:
        con.close()

if __name__ == "__main__":
    main()
