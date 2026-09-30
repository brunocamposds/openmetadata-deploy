"""
Pipeline de Transformação Silver Consolidada - RENDA_FIXA_DERIVADO
Plataforma: Azure Databricks (Unity Catalog)
Descrição: Consome as tabelas Silver dos produtos de dados upstream SIST_CDB e SIST_CRA,
           unifica os esquemas em conformidade com o contrato ODCS e persiste nas tabelas
           investments.renda_fixa.silver_posicao e silver_movimentacao.
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, lit, sha2, concat_ws, when
from delta.tables import DeltaTable

def get_spark_session() -> SparkSession:
    return SparkSession.builder \
        .appName("RF_Derivado_Silver_Consolidation") \
        .getOrCreate()

def consolidate_positions(spark: SparkSession):
    print(">>> Consolidando posições de CDB e CRA na Silver de Renda Fixa...")
    cdb_df = spark.table("investments.cdb.silver_posicao")
    cra_df = spark.table("investments.cra.silver_posicao")

    # Mapeamento e unificação de CDB
    cdb_mapped = cdb_df.select(
        sha2(concat_ws("||", lit("CDB"), col("id_posicao")), 256).alias("id_posicao_unificada"),
        col("dt_posicao"),
        col("id_cliente"),
        lit("CDB").alias("tp_produto_renda_fixa"),
        col("cd_certificado").alias("cd_instrumento"),
        col("vl_principal_aplicado"),
        col("vl_saldo_bruto"),
        col("vl_saldo_liquido"),
        col("dt_vencimento")
    )

    # Mapeamento e unificação de CRA
    cra_mapped = cra_df.select(
        sha2(concat_ws("||", lit("CRA"), col("id_posicao")), 256).alias("id_posicao_unificada"),
        col("dt_posicao"),
        col("id_cliente"),
        lit("CRA").alias("tp_produto_renda_fixa"),
        col("cd_cra_isin").alias("cd_instrumento"),
        col("vl_principal_aplicado"),
        col("vl_saldo_bruto"),
        col("vl_saldo_liquido"),
        col("dt_vencimento")
    )

    # Union de posições
    consolidated_pos_df = cdb_mapped.unionByName(cra_mapped)

    target_table = "investments.renda_fixa.silver_posicao"
    if spark.catalog.tableExists(target_table):
        delta_target = DeltaTable.forName(spark, target_table)
        (
            delta_target.alias("tgt")
            .merge(
                consolidated_pos_df.alias("src"),
                "tgt.id_posicao_unificada = src.id_posicao_unificada"
            )
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )
    else:
        consolidated_pos_df.write \
            .format("delta") \
            .partitionBy("dt_posicao") \
            .saveAsTable(target_table)

    print(f">>> Carga concluída com sucesso em {target_table}")

def consolidate_movements(spark: SparkSession):
    print(">>> Consolidando movimentações de CDB e CRA na Silver de Renda Fixa...")
    cdb_mov = spark.table("investments.cdb.silver_movimentacao")
    cra_mov = spark.table("investments.cra.silver_movimentacao")

    cdb_mapped = cdb_mov.select(
        sha2(concat_ws("||", lit("CDB"), col("id_movimentacao")), 256).alias("id_movimentacao_unificada"),
        col("dt_movimentacao"),
        col("id_cliente"),
        lit("CDB").alias("tp_produto"),
        when(col("tp_movimentacao") == "APORTE", lit("APORTE"))
        .when(col("tp_movimentacao").like("RESGATE%"), lit("RESGATE"))
        .otherwise(lit("RENDIMENTO")).alias("tp_operacao_macro"),
        col("vl_movimentacao")
    )

    cra_mapped = cra_mov.select(
        sha2(concat_ws("||", lit("CRA"), col("id_movimentacao")), 256).alias("id_movimentacao_unificada"),
        col("dt_movimentacao"),
        col("id_cliente"),
        lit("CRA").alias("tp_produto"),
        when(col("tp_movimentacao") == "APORTE_SUBSCRICAO", lit("APORTE"))
        .when(col("tp_movimentacao").isin("AMORTIZACAO_PARCIAL", "LIQUIDACAO_FINAL"), lit("RESGATE"))
        .otherwise(lit("RENDIMENTO")).alias("tp_operacao_macro"),
        col("vl_movimentacao")
    )

    consolidated_mov_df = cdb_mapped.unionByName(cra_mapped)

    target_table = "investments.renda_fixa.silver_movimentacao"
    if spark.catalog.tableExists(target_table):
        delta_target = DeltaTable.forName(spark, target_table)
        (
            delta_target.alias("tgt")
            .merge(
                consolidated_mov_df.alias("src"),
                "tgt.id_movimentacao_unificada = src.id_movimentacao_unificada"
            )
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )
    else:
        consolidated_mov_df.write \
            .format("delta") \
            .partitionBy("dt_movimentacao") \
            .saveAsTable(target_table)

    print(f">>> Carga concluída com sucesso em {target_table}")

if __name__ == "__main__":
    spark = get_spark_session()
    consolidate_positions(spark)
    consolidate_movements(spark)
