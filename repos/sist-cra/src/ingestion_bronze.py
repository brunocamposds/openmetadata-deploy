"""
Pipeline de Ingestão Bronze - SIST_CRA
Plataforma: Azure Databricks (Unity Catalog)
Descrição: Lê dados brutos de retorno das securitizadoras (XML/JSON via ADLS Gen2 Landing)
           e persiste nas tabelas Bronze Delta Lake do Unity Catalog.
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, current_timestamp, input_file_name, lit

def get_spark_session() -> SparkSession:
    return SparkSession.builder \
        .appName("SIST_CRA_Ingestion_Bronze") \
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
        .getOrCreate()

def ingest_posicoes_cra_bronze(spark: SparkSession, landing_path: str):
    print(">>> Ingerindo posições brutas de CRA para bronze...")
    raw_df = spark.read.format("json").load(landing_path)

    bronze_df = raw_df \
        .withColumn("_raw_file", input_file_name()) \
        .withColumn("_ingested_at", current_timestamp()) \
        .withColumn("_source_system", lit("SIST_CRA_SECURITIZADORA_GATEWAY"))

    (
        bronze_df.write
        .format("delta")
        .mode("append")
        .option("mergeSchema", "true")
        .saveAsTable("investments.cra.bronze_posicao")
    )
    print(">>> Concluída ingestão em investments.cra.bronze_posicao")

def ingest_movimentacoes_cra_bronze(spark: SparkSession, landing_path: str):
    print(">>> Ingerindo movimentações brutas de CRA para bronze...")
    raw_df = spark.read.format("json").load(landing_path)

    bronze_df = raw_df \
        .withColumn("_raw_file", input_file_name()) \
        .withColumn("_ingested_at", current_timestamp()) \
        .withColumn("_source_system", lit("SIST_CRA_SECURITIZADORA_GATEWAY"))

    (
        bronze_df.write
        .format("delta")
        .mode("append")
        .option("mergeSchema", "true")
        .saveAsTable("investments.cra.bronze_movimentacao")
    )
    print(">>> Concluída ingestão em investments.cra.bronze_movimentacao")

if __name__ == "__main__":
    spark = get_spark_session()
    
    LANDING_POSICAO = "abfss://landing@stinvestmentsdatalake.dfs.core.windows.net/cra/posicoes/*"
    LANDING_MOV = "abfss://landing@stinvestmentsdatalake.dfs.core.windows.net/cra/movimentacoes/*"
    
    ingest_posicoes_cra_bronze(spark, LANDING_POSICAO)
    ingest_movimentacoes_cra_bronze(spark, LANDING_MOV)
