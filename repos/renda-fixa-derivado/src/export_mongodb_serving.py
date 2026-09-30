"""
Pipeline de Exportação Operacional para MongoDB Serving Layer
Plataforma: Azure Databricks (PySpark) -> MongoDB Atlas
Descrição: Constrói a visão documental desnormalizada por cliente combinando
           a Gold de Saldo Investido e a Silver de Posições granulares, gravando na
           coleção 'rf_customer_positions' do banco 'investments_serving' via
           conector oficial spark-mongodb.
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, struct, collect_list, current_timestamp, date_format
)

def get_spark_session() -> SparkSession:
    # Em ambiente Databricks, incluir a coordenada maven:
    # org.mongodb.spark:mongo-spark-connector_2.12:10.3.0
    return SparkSession.builder \
        .appName("RF_Derivado_Export_MongoDB") \
        .getOrCreate()

def export_customer_positions_to_mongodb(spark: SparkSession, mongo_uri: str):
    print(">>> Preparando payload desnormalizado para serving layer no MongoDB...")

    silver_pos = spark.table("investments.renda_fixa.silver_posicao")
    gold_saldo = spark.table("investments.renda_fixa.gold_saldo_investido")

    # Estruturação da lista aninhada de produtos/títulos por cliente
    products_nested_df = silver_pos.select(
        col("id_cliente"),
        col("dt_posicao"),
        struct(
            col("tp_produto_renda_fixa").alias("productType"),
            col("cd_instrumento").alias("instrumentCode"),
            col("vl_principal_aplicado").cast("double").alias("appliedValue"),
            col("vl_saldo_bruto").cast("double").alias("grossBalance"),
            col("vl_saldo_liquido").cast("double").alias("netBalance"),
            col("dt_vencimento").cast("string").alias("dueDate")
        ).alias("product_item")
    ).groupBy("id_cliente", "dt_posicao").agg(
        collect_list("product_item").alias("productsSummary")
    )

    # Junção com as métricas sumarizadas Gold
    serving_documents_df = gold_saldo.join(
        products_nested_df,
        on=["id_cliente", "dt_posicao"],
        how="inner"
    ).select(
        col("id_cliente").alias("_id"),
        col("id_cliente").alias("customerId"),
        date_format(col("dt_posicao"), "yyyy-MM-dd").alias("snapshotDate"),
        col("vl_total_aplicado_instituicao").cast("double").alias("totalInvested"),
        col("vl_total_bruto_instituicao").cast("double").alias("totalGrossBalance"),
        col("vl_total_liquido_instituicao").cast("double").alias("totalNetBalance"),
        col("productsSummary"),
        current_timestamp().alias("lastUpdatedUtc")
    )

    print(f">>> Gravando documentos na coleção investments_serving.rf_customer_positions...")
    (
        serving_documents_df.write
        .format("mongodb")
        .mode("append")
        .option("connection.uri", mongo_uri)
        .option("database", "investments_serving")
        .option("collection", "rf_customer_positions")
        .option("operationType", "replace") # Upsert baseado no _id
        .save()
    )
    print(">>> Sincronização operacional com MongoDB concluída com sucesso.")

if __name__ == "__main__":
    spark = get_spark_session()
    # Em produção, a string de conexão é obtida com segurança via Databricks Secrets
    # MONGO_URI = dbutils.secrets.get(scope="investments-scope", key="mongodb-serving-conn")
    SAMPLE_MONGO_URI = "mongodb://mongodb-atlas.internal:27017/investments_serving"
    
    export_customer_positions_to_mongodb(spark, SAMPLE_MONGO_URI)
