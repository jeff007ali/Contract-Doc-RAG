import os
import re
import json
import uuid
import fitz  # PyMuPDF
import requests
import openai
from dotenv import load_dotenv
import tiktoken

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI()
ELASTIC_HOST = os.getenv("ELASTIC_HOST", "http://localhost:9200")
embedding_model = "text-embedding-3-small"

# PDF Extraction 
def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    return "\n".join(page.get_text() for page in doc)

# Text Cleanup
def clean_text(text):
    # Replace non-breaking spaces with regular spaces
    text = text.replace('\xa0', ' ')
    # Normalize excessive newlines
    text = re.sub(r'\n+', '\n', text)
    # Merge broken lines that are not numbered
    text = re.sub(r'(?<!\d)\n(?!\d)', ' ', text)
    return text.strip()

# Get Embedding
def embed_text(text):
    try:
        res = client.embeddings.create(input=text, model=embedding_model)
        print("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
        print("Embedding resposne = {}".format(res))
        return res.data[0].embedding
    except Exception as e:
        print(f"Embedding Text failed: {e}")
        return None


def embed_chunks(chunks):
    try:
        response = client.embeddings.create(
            model=embedding_model,
            input=chunks  # pass list of strings
        )
        return [res.embedding for res in response.data]
    except Exception as e:
        print(f"Embedding Chunks failed: {e}")
        return None


# def chunk_by_tokens(text, max_tokens=800):
#     enc = tiktoken.encoding_for_model(embedding_model)
#     tokens = enc.encode(text)
#     chunks = []

#     for i in range(0, len(tokens), max_tokens):
#         chunk_tokens = tokens[i:i+max_tokens]
#         chunks.append(enc.decode(chunk_tokens))

#     return chunks


def chunk_by_tokens_with_overlap(text, max_tokens=800, overlap=100):
    enc = tiktoken.encoding_for_model(embedding_model)
    tokens = enc.encode(text)
    
    chunks = []
    i = 0
    while i < len(tokens):
        chunk = tokens[i:i+max_tokens]
        chunks.append(enc.decode(chunk))
        i += max_tokens - overlap  # move forward with overlap

    return chunks


def bulk_index_chunks(contract_id, chunks, embeddings):
    bulk_payload = ""
    for i, (chunk, vector) in enumerate(zip(chunks, embeddings)):
        meta = {"index": {"_index": "contract_chunks"}}
        doc = {
            "contract_id": contract_id,
            "chunk_text": chunk,
            "embedding": vector,
            "metadata": {}
        }
        bulk_payload += f"{json.dumps(meta)}\n{json.dumps(doc)}\n"

    headers = {"Content-Type": "application/x-ndjson"}
    response = requests.post(f"{ELASTIC_HOST}/_bulk", headers=headers, data=bulk_payload)
    
    if response.status_code == 200:
        result = response.json()
        if result.get("errors"):
            print("Some documents failed:", result)
        else:
            print(f"Bulk index successful: {len(chunks)} chunks")
    else:
        print("Bulk index failed:", response.status_code, response.text)


def search_similar_chunks(user_query, contract_id, top_k=5):
    embedding = embed_text(user_query)

    url = f"{ELASTIC_HOST}/contract_chunks/_search"
    headers = {"Content-Type": "application/json"}

    query = {
        "size": top_k,
        "query": {
            "bool": {
                "filter": {
                    "term": {
                        "contract_id": contract_id
                    }
                },
                "must": {
                    "script_score": {
                        "query": {"match_all": {}},
                        "script": {
                            "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                            "params": {
                                "query_vector": embedding
                            }
                        }
                    }
                }
            } 
        }
    }

    response = requests.get(url, headers=headers, json=query).json()
    hits = response.get("hits", {}).get("hits", [])
    return [hit["_source"]["chunk_text"] for hit in hits]


def extract_clause_with_openai(query, chunks):
    context = "\n\n".join(chunks)
    messages = [
        {"role": "system", "content": "You are a legal assistant. Extract the requested clause from the contract."},
        {"role": "user", "content": f"{query}\n\nContract:\n{context}"}
    ]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0
    )

    print("@@@@@@@@@@@@@@@@@@@@@@@@@@@@")
    print(response)

    return response.choices[0].message.content.strip()


# Execute the flow
def embed_and_index_file(pdf_path, contract_id="contract_123"):
    text = extract_text_from_pdf(pdf_path)
    text = clean_text(text)
    chunks = chunk_by_tokens_with_overlap(text)

    print(text)
    print("@@@@@@@@@@@@@@@@@@@@")
    for c in chunks:
        print("---------------")
        print(c)
    print(len(chunks))

    embeddings = embed_chunks(chunks)
    
    # contract_id = str(uuid.uuid4())
    bulk_index_chunks(contract_id, chunks, embeddings)


def ask_question(query, contract_id="contract_123"):
    relevant_chunks = search_similar_chunks(query, contract_id)
    result = extract_clause_with_openai(query, relevant_chunks)

    print("\nExtracted Clause:\n", result)
    

if __name__ == "__main__":
    embed_and_index_file("CUAD_v1\\full_contract_pdf\\Part_I\\Affiliate_Agreements\\CreditcardscomInc_20070810_S-1_EX-10.33_362297_EX-10.33_Affiliate Agreement.pdf")
    ask_question("Extract the Payment Terms clause")
