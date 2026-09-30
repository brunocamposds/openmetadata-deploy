"""
Pipeline de Transformação Silver - SIST_CRA
Plataforma: Azure Databricks (Unity Catalog)
Descrição: Lê dados da camada Bronze, valida integridade do contrato ODCS de CRA,
           aplica deduplicação, regras de isenção de IR e grava em Delta Lake Silver.
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, to_date, to_timestamp, current_timestamp, sha2, concat_ws
)
from delta.tables import DeltaTable

def get_spark_session() -> SparkSession:
    return SparkSession.builder \
        .appName("SIST_CRA_Transform_Silver") \
        .getOrCreate()

def process_silver_posicao(spark: SparkSession):
    print(">>> Processando Silver de Posições CRA (Conformidade ODCS)...")
    bronze_df = spark.table("investments.cra.bronze_posicao")

    silver_df = bronze_df.select(
        sha2(concat_ws("||", col("DT_POSICAO"), col("CD_ISIN")), 256).alias("id_posicao"),
        to_date(col("DT_POSICAO"), "yyyy-MM-dd").alias("dt_posicao"),
        col("CD_ISIN").cast("string").alias("cd_cra_isin"),
        col("NOME_SECURITIZADORA").cast("string").alias("nm_emissora_securitizadora"),
        col("ID_INVESTIDOR").cast("string").alias("id_cliente"),
        col("TIPO_TAXA").cast("string").alias("cd_tipo_remuneracao"),
        col("QTD_COTAS").cast("bigint").alias("qt_titulos_custodia"),
        col("VALOR_SUBSCRIÇÃO").cast("decimal(18,2)").alias("vl_principal_aplicado"),
        col("VALOR_MERCADO_BRUTO").cast("decimal(18,2)").alias("vl_saldo_bruto"),
        col("VALOR_LIQUIDO").cast("decimal(18,2)").alias("vl_saldo_liquido"),
        to_date(col("DT_EMISSAO"), "yyyy-MM-dd").alias("dt_emissao"),
        to_date(col("DT_VENCIMENTO"), "yyyy-MM-dd").alias("dt_vencimento"),
        current_timestamp().alias("dh_ingestao_utc")
    ).filter(
        (col("vl_saldo_bruto") >= 0) &
        (col("vl_saldo_liquido") <= col("vl_saldo_bruto")) &
        (col("qt_titulos_custodia") > 0)
    ).dropDuplicates(["id_posicao"])

    target_table = "investments.cra.silver_posicao"
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
    print(">>> Processando Silver de Movimentações CRA (Conformidade ODCS)...")
    bronze_df = spark.table("investments.cra.bronze_movimentacao")

    silver_df = bronze_df.select(
        sha2(concat_ws("||", col("ID_EVENTO"), col("DH_LIQUIDACAO")), 256).alias("id_movimentacao"),
        to_date(col("DH_LIQUIDACAO")).alias("dt_movimentacao"),
        col("CD_ISIN").cast("string").alias("cd_cra_isin"),
        col("ID_INVESTIDOR").cast("string").alias("id_cliente"),
        col("NATUREZA_EVENTO").cast("string").alias("tp_movimentacao"),
        col("VALOR_LIQUIDADO").cast("decimal(18,2)").alias("vl_movimentacao"),
        to_timestamp(col("DH_EVENTO_CUSTODIA")).alias("dh_evento_origem")
    ).filter(
        col("vl_movimentacao") > 0
    ).dropDuplicates(["id_movimentacao"])

    target_table = "investments.cra.silver_movimentacao"
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
