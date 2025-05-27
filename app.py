import os
import re
import json
import hashlib
import fitz  # PyMuPDF
import openai
import tiktoken
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_url_path='/static')
CORS(app)

openai.api_key = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI()

ELASTIC_HOST = os.getenv("ELASTIC_HOST", "http://localhost:9200")
embedding_model = "text-embedding-3-small"

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def extract_text_from_pdf(file_path):
    doc = fitz.open(file_path)
    return "\n".join(page.get_text() for page in doc)

def clean_text(text):
    text = text.replace('\xa0', ' ')
    text = re.sub(r'\n+', '\n', text)
    text = re.sub(r'(?<!\d)\n(?!\d)', ' ', text)
    return text.strip()

def chunk_by_tokens_with_overlap(text, max_tokens=800, overlap=100):
    enc = tiktoken.encoding_for_model(embedding_model)
    tokens = enc.encode(text)
    chunks = []
    i = 0
    while i < len(tokens):
        chunk = tokens[i:i+max_tokens]
        chunks.append(enc.decode(chunk))
        i += max_tokens - overlap
    return chunks

def embed_chunks(chunks):
    response = client.embeddings.create(
        model=embedding_model,
        input=chunks
    )
    return [res.embedding for res in response.data]

def bulk_index_chunks(contract_id, chunks, embeddings):
    bulk_payload = ""
    for chunk, vector in zip(chunks, embeddings):
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
    return response.status_code == 200

def check_duplicate(contract_id):
    url = f"{ELASTIC_HOST}/contract_chunks/_search"
    query = {
        "size": 1,
        "query": {
            "term": {
                "contract_id": contract_id
            }
        }
    }
    res = requests.get(url, json=query).json()
    return len(res.get("hits", {}).get("hits", [])) > 0

def search_similar_chunks(query, contract_id):
    embedding = client.embeddings.create(input=query, model=embedding_model).data[0].embedding
    payload = {
        "size": 5,
        "query": {
            "bool": {
                "filter": {"term": {"contract_id": contract_id}},
                "must": {
                    "script_score": {
                        "query": {"match_all": {}},
                        "script": {
                            "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                            "params": {"query_vector": embedding}
                        }
                    }
                }
            }
        }
    }
    response = requests.get(f"{ELASTIC_HOST}/contract_chunks/_search", json=payload)
    hits = response.json().get("hits", {}).get("hits", [])
    return [hit["_source"]["chunk_text"] for hit in hits]

def extract_clause_with_openai(query, chunks):
    context = "\n\n".join(chunks)
    messages = [
        {"role": "system", "content": "You are a legal assistant. Extract the requested clause from the contract."},
        {"role": "user", "content": f"{query}\n\nContract:\n{context}"}
    ]
    response = client.chat.completions.create(model="gpt-4o", messages=messages, temperature=0)
    return response.choices[0].message.content.strip()

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files["file"]
    file_bytes = file.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    if check_duplicate(file_hash):
        return jsonify({"contract_id": file_hash, "status": "duplicate"})

    file_path = os.path.join(UPLOAD_DIR, f"{file_hash}.pdf")
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    text = clean_text(extract_text_from_pdf(file_path))
    chunks = chunk_by_tokens_with_overlap(text)
    embeddings = embed_chunks(chunks)

    # print("chunks = {} and embeddings = {}".format(chunks, embeddings))
    bulk_index_chunks(file_hash, chunks, embeddings)

    return jsonify({"contract_id": file_hash, "status": "indexed"})

@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    question = data["question"]
    contract_id = data["contract_id"]

    relevant_chunks = search_similar_chunks(question, contract_id)
    answer = extract_clause_with_openai(question, relevant_chunks)

    matched_chunk = relevant_chunks[0] if relevant_chunks else ""
    return jsonify({"answer": answer, "matched_chunk": matched_chunk})
    # return jsonify({"answer": "answer", "matched_chunk": "matched_chunk"})

@app.route("/static/<path:path>")
def send_static(path):
    return send_from_directory("static", path)

if __name__ == "__main__":
    app.run(debug=True)
