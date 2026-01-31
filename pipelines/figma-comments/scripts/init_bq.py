import os
from google.cloud import bigquery
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "emailpilot-438321")
DATASET_ID = "figma"

def init_bq():
    client = bigquery.Client(project=PROJECT_ID)
    
    # 1. Create Dataset
    dataset_ref = client.dataset(DATASET_ID)
    try:
        client.get_dataset(dataset_ref)
        logger.info(f"Dataset {DATASET_ID} already exists.")
    except Exception:
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "US"
        client.create_dataset(dataset)
        logger.info(f"Created dataset {DATASET_ID}.")

    # 2. Create Comments Table
    comments_table_id = f"{PROJECT_ID}.{DATASET_ID}.comments"
    comments_schema = [
        bigquery.SchemaField("comment_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("client_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("file_key", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("comment_text", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("resolved_at", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("user_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("copy_and_design", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
    ]
    
    try:
        client.get_table(comments_table_id)
        logger.info(f"Table {comments_table_id} already exists.")
    except Exception:
        table = bigquery.Table(comments_table_id, schema=comments_schema)
        client.create_table(table)
        logger.info(f"Created table {comments_table_id}.")

    # 3. Create Creative Rules Table
    rules_table_id = f"{PROJECT_ID}.{DATASET_ID}.creative_rules"
    rules_schema = [
        bigquery.SchemaField("rule_text", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("sentiment", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("category", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("source_file", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("source_comment_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("client_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
    ]
    
    try:
        client.get_table(rules_table_id)
        logger.info(f"Table {rules_table_id} already exists.")
    except Exception:
        table = bigquery.Table(rules_table_id, schema=rules_schema)
        client.create_table(table)
        logger.info(f"Created table {rules_table_id}.")

if __name__ == "__main__":
    init_bq()
