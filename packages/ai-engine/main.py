from sentence_transformers import SentenceTransformer
import chromadb

# Initialize the cross-lingual embedding model
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
client = chromadb.Client()
collection = client.get_or_create_collection(name="cultural_context")

def get_contextual_response(query):
    query_embedding = model.encode(query).tolist()
    # Retrieval logic from ChromaDB
    results = collection.query(query_embeddings=[query_embedding], n_results=2)
    return results