"""
Pipeline de Métricas Gold - RENDA_FIXA_DERIVADO
Plataforma: Azure Databricks (Unity Catalog)
Descrição: Agrega dados da camada Silver de Renda Fixa consolidada para produzir
           as tabelas Gold:
           1. investments.renda_fixa.gold_saldo_investido (Saldo na data de posição)
           2. investments.renda_fixa.gold_movimentacao_sumarizada (Resgates e aportes sumarizados)
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, sum as _sum, countDistinct, when
)
from delta.tables import DeltaTable

def get_spark_session() -> SparkSession:
    return SparkSession.builder \
        .appName("RF_Derivado_Gold_Metrics") \
        .getOrCreate()

def process_gold_saldo_investido(spark: SparkSession):
    print(">>> Processando Gold: Saldo Investido na Instituição...")
    silver_pos_df = spark.table("investments.renda_fixa.silver_posicao")

    gold_saldo_df = silver_pos_df.groupBy("dt_posicao", "id_cliente").agg(
        _sum("vl_principal_aplicado").cast("decimal(18,2)").alias("vl_total_aplicado_instituicao"),
        _sum("vl_saldo_bruto").cast("decimal(18,2)").alias("vl_total_bruto_instituicao"),
        _sum("vl_saldo_liquido").cast("decimal(18,2)").alias("vl_total_liquido_instituicao"),
        countDistinct("cd_instrumento").cast("int").alias("qt_titulos_ativos")
    )

    target_table = "investments.renda_fixa.gold_saldo_investido"
    if spark.catalog.tableExists(target_table):
        delta_target = DeltaTable.forName(spark, target_table)
        (
            delta_target.alias("tgt")
            .merge(
                gold_saldo_df.alias("src"),
                "tgt.dt_posicao = src.dt_posicao AND tgt.id_cliente = src.id_cliente"
            )
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )
    else:
        gold_saldo_df.write \
            .format("delta") \
            .partitionBy("dt_posicao") \
            .saveAsTable(target_table)

    print(f">>> Carga concluída com sucesso em {target_table}")

def process_gold_movimentacao_sumarizada(spark: SparkSession):
    print(">>> Processando Gold: Resumo de Aportes e Resgates...")
    silver_mov_df = spark.table("investments.renda_fixa.silver_movimentacao")

    gold_mov_df = silver_mov_df.groupBy("dt_movimentacao", "id_cliente").agg(
        _sum(when(col("tp_operacao_macro") == "APORTE", col("vl_movimentacao")).otherwise(0.0))
            .cast("decimal(18,2)").alias("vl_total_aportes_dia"),
        _sum(when(col("tp_operacao_macro") == "RESGATE", col("vl_movimentacao")).otherwise(0.0))
            .cast("decimal(18,2)").alias("vl_total_resgates_dia")
    ).withColumn(
        "vl_fluxo_liquido_dia",
        (col("vl_total_aportes_dia") - col("vl_total_resgates_dia")).cast("decimal(18,2)")
    )

    target_table = "investments.renda_fixa.gold_movimentacao_sumarizada"
    if spark.catalog.tableExists(target_table):
        delta_target = DeltaTable.forName(spark, target_table)
        (
            delta_target.alias("tgt")
            .merge(
                gold_mov_df.alias("src"),
                "tgt.dt_movimentacao = src.dt_movimentacao AND tgt.id_cliente = src.id_cliente"
            )
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )
    else:
        gold_mov_df.write \
            .format("delta") \
            .partitionBy("dt_movimentacao") \
            .saveAsTable(target_table)

    print(f">>> Carga concluída com sucesso em {target_table}")

if __name__ == "__main__":
    spark = get_spark_session()
    process_gold_saldo_investido(spark)
    process_gold_movimentacao_sumarizada(spark)
