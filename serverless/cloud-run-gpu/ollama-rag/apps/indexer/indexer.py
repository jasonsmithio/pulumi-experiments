import os
from google.cloud.alloydb.connector import Connector
from google.cloud import storage
import pg8000
from langchain.llms import Ollama
from langchain_community.vectorstores.pgvector import PGVector
from langchain_google_vertexai import VertexAIEmbeddings
import pymupdf


# Parse PDFs in Cloud Storage Bucket 

pdf_text= []

def list_pdfs(directory):
    pdf_files = []
    for filename in os.listdir(directory):
        if filename.endswith(".pdf"):
            pdf_files.append(filename)
    return pdf_files

pdf_path = "/root/.training/pdfs"
pdfs = list_pdfs(pdf_path)

for pdf in pdfs:
    pdf = pymupdf.open(pdf)
    for page in pdf:
        text = page.get_text()
        pdf_text.append(text)

print(f"Number of release lines retrieved:", len(pdf_text))

# Set up a PGVector instance 
connector = Connector()

def getconn() -> pg8000.dbapi.Connection:
    conn: pg8000.dbapi.Connection = connector.connect(
        os.getenv("RAG_DB_INSTANCE_NAME", ""),
        "pg8000",
        user=os.getenv("RAG_DB_USER", ""),
        password=os.getenv("RAG_DB_PASS", ""),
        db=os.getenv("RAG_DB_NAME", ""),
    )
    return conn

store = PGVector(
    connection_string="postgresql+pg8000://",
    use_jsonb=True,
    engine_args=dict(
        creator=getconn,
    ),
    embedding_function=VertexAIEmbeddings(
        model_name="textembedding-gecko@003"
    ),
    pre_delete_collection=True  
)

# Save all PDF into the AlloyDB database
texts = list(pdf_text)
ids = store.add_texts(texts)

print(f"Done saving: {len(ids)} items")