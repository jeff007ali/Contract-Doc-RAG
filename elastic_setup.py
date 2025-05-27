import requests
import os
from dotenv import load_dotenv

load_dotenv()
ELASTIC_HOST = os.getenv("ELASTIC_HOST", "http://localhost:9200")

def create_index():
    url = f"{ELASTIC_HOST}/clauses"
    mapping = {
        "mappings": {
            "properties": {
                "clause_text": {"type": "text"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": 1536,
                    "index": True,
                    "similarity": "cosine"
                },
                "clause_type": {"type": "keyword"}
            }
        }
    }

    res = requests.put(url, json=mapping)
    print("Clauses Elasticsearch Index Created:", res.status_code, res.text)


def create_contract_chunks_index():
    url = f"{ELASTIC_HOST}/contract_chunks"
    mapping = {
        "mappings": {
            "properties": {
                "contract_id": {"type": "keyword"},
                "chunk_text": {"type": "text"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": 1536,
                    "index": True,
                    "similarity": "cosine"
                },
                "metadata": {"type": "object"}
            }
        }
    }

    res = requests.put(url, json=mapping)
    print("Contract Chunks Elasticsearch Index Created:", res.status_code, res.text)


if __name__ == "__main__":
    create_index()
    create_contract_chunks_index()
