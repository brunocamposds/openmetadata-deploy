"""
Pipeline de Transformação Silver - SIST_CDB
Plataforma: Azure Databricks (Unity Catalog)
Descrição: Lê dados da camada Bronze, aplica validações de conformidade com o contrato
           ODCS, tipagem forte, deduplicação e salva nas tabelas Silver.
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, to_date, to_timestamp, current_timestamp, sha2, concat_ws, when, coalesce
)
from delta.tables import DeltaTable

def get_spark_session() -> SparkSession:
    return SparkSession.builder \
        .appName("SIST_CDB_Transform_Silver") \
        .getOrCreate()

def process_silver_posicao(spark: SparkSession):
    print(">>> Processando Silver de Posições CDB (Conformidade ODCS)...")
    bronze_df = spark.table("investments.cdb.bronze_posicao")

    # Tratamento e tipagem conforme contrato ODCS
    silver_df = bronze_df.select(
        sha2(concat_ws("||", col("DATA_POSICAO"), col("NUM_CERTIFICADO")), 256).alias("id_posicao"),
        to_date(col("DATA_POSICAO"), "yyyy-MM-dd").alias("dt_posicao"),
        col("NUM_CERTIFICADO").cast("string").alias("cd_certificado"),
        col("COD_CLIENTE").cast("string").alias("id_cliente"),
        col("TIPO_INDEXADOR").cast("string").alias("cd_tipo_cdb"),
        col("VALOR_APLICADO").cast("decimal(18,2)").alias("vl_principal_aplicado"),
        col("VALOR_BRUTO_ATUAL").cast("decimal(18,2)").alias("vl_saldo_bruto"),
        col("VALOR_LIQUIDO_ATUAL").cast("decimal(18,2)").alias("vl_saldo_liquido"),
        col("TAXA_PACTUADA").cast("decimal(8,4)").alias("tx_remuneracao"),
        to_date(col("DATA_EMISSAO"), "yyyy-MM-dd").alias("dt_aplicacao"),
        to_date(col("DATA_VENCIMENTO"), "yyyy-MM-dd").alias("dt_vencimento"),
        current_timestamp().alias("dh_ingestao_utc")
    ).filter(
        # Validação das regras de contrato ODCS
        (col("vl_saldo_bruto") >= 0) &
        (col("vl_saldo_liquido") <= col("vl_saldo_bruto")) &
        (col("dt_vencimento") >= col("dt_aplicacao"))
    ).dropDuplicates(["id_posicao"])

    # Merge Delta (SCD Tipo 1 com partição por dt_posicao)
    target_table = "investments.cdb.silver_posicao"
    if spark.catalog.tableExists(target_table):
        delta_target = DeltaTable.forName(spark, target_table)
        (
            delta_target.alias("tgt")
            .merge(
                silver_df.alias("src"),
                "tgt.id_posicao = src.id_posicao"
            )
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )
    else:
        silver_df.write \
            .format("delta") \
            .partitionBy("dt_posicao") \
            .saveAsTable(target_table)

    print(f">>> Carga concluída com sucesso em {target_table}")

def process_silver_movimentacao(spark: SparkSession):
    print(">>> Processando Silver de Movimentações CDB (Conformidade ODCS)...")
    bronze_df = spark.table("investments.cdb.bronze_movimentacao")

    silver_df = bronze_df.select(
        sha2(concat_ws("||", col("ID_TRANSACAO"), col("DH_TRANSACAO")), 256).alias("id_movimentacao"),
        to_date(col("DH_TRANSACAO")).alias("dt_movimentacao"),
        col("NUM_CERTIFICADO").cast("string").alias("cd_certificado"),
        col("COD_CLIENTE").cast("string").alias("id_cliente"),
        col("TIPO_OPERACAO").cast("string").alias("tp_movimentacao"),
        col("VALOR_TRANSACAO").cast("decimal(18,2)").alias("vl_movimentacao"),
        col("VALOR_IR").cast("decimal(18,2)").alias("vl_ir_retido"),
        col("VALOR_IOF").cast("decimal(18,2)").alias("vl_iof_retido"),
        to_timestamp(col("DH_TRANSACAO")).alias("dh_evento_origem")
    ).filter(
        col("vl_movimentacao") > 0
    ).dropDuplicates(["id_movimentacao"])

    target_table = "investments.cdb.silver_movimentacao"
    if spark.catalog.tableExists(target_table):
        delta_target = DeltaTable.forName(spark, target_table)
        (
            delta_target.alias("tgt")
            .merge(
                silver_df.alias("src"),
                "tgt.id_movimentacao = src.id_movimentacao"
            )
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )
    else:
        silver_df.write \
            .format("delta") \
            .partitionBy("dt_movimentacao") \
            .saveAsTable(target_table)

    print(f">>> Carga concluída com sucesso em {target_table}")

if __name__ == "__main__":
    spark = get_spark_session()
    process_silver_posicao(spark)
    process_silver_movimentacao(spark)
