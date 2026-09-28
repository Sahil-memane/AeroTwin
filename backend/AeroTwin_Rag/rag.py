from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from dotenv import load_dotenv
import os




load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY not found in .env")



data = PyPDFLoader(
    "AeroTwin_Vector_DB_Final_Knowledge_Base.pdf"
)

docs = data.load()

print("PDF loaded successfully!")




splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200
)

chunks = splitter.split_documents(docs)

print("Total chunks:", len(chunks))




embedding_model = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-001",
    google_api_key=api_key
)




vector_store = Chroma.from_documents(
    documents=chunks,
    embedding=embedding_model,
    persist_directory="ChromaDB_AeroTwin"
)

print("\n========================================")
print("Gemini ChromaDB created successfully!")
print("========================================")