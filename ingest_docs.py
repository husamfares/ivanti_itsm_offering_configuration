import os ,shutil, hashlib
from pathlib import Path
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.tools.retriever import create_retriever_tool

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

DATA = {
    "pdf": Path(r"C:\Users\DELL-G15\Downloads\Request Offering\Request Offering\Ivanti Workflows Documentation.pdf"),
    "brd": Path(r"C:\Users\DELL-G15\Downloads\Request Offering\Request Offering\Request Offering BRD.docx"),
}

pdf_path = DATA["pdf"]          
brd_path = DATA["brd"]         


PERSIST_DIR= "kb/chroma_ivanti"

def load_all_docs():
    docs = []

    if pdf_path.exists():
        for source in PyPDFLoader(str(pdf_path)).load():
            source.metadata["source"] = pdf_path.name      
            source.metadata["source_path"] = str(pdf_path) 
            docs.append(source)

    
    if brd_path.exists():
        for source in Docx2txtLoader(str(brd_path)).load():
            source.metadata["source"] = brd_path.name       
            source.metadata["source_path"] = str(brd_path)   
            docs.append(source)

    if not docs:
        raise FileNotFoundError("No source docs found.")
    return docs


def make_id(doc, idx):
    src = doc.metadata.get("source", "unknown")
    page = str(doc.metadata.get("page", ""))  
    h = hashlib.sha1(f"{src}|{page}|{idx}".encode("utf-8")).hexdigest()[:12]
    return f"{Path(src).stem}-{page}-{idx}-{h}"



def main_grounding_data(rebuild = False):

    all_docs = load_all_docs()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size= 1200,
        chunk_overlap= 200,
        separators=["\n\n", "\n", " ", ""],
    )
    chunks = splitter.split_documents(all_docs)

    if (not rebuild) and Path(PERSIST_DIR).exists():
        print(f"KB already exists at {PERSIST_DIR}; skip embedding.")
        return

    vectordb = Chroma(
        collection_name="ivanti_kb",
        embedding_function=OpenAIEmbeddings(model="text-embedding-3-small"),
        persist_directory=PERSIST_DIR
    )

    ids = [make_id(c, i) for i, c in enumerate(chunks)]
    vectordb.add_documents(chunks, ids= ids)

    try:
        vectordb.persist()
    except Exception:
        pass


def build_retriever_tool():
        
    vectordb = Chroma(
        collection_name="ivanti_kb",
        embedding_function=OpenAIEmbeddings(model="text-embedding-3-small"),
        persist_directory=PERSIST_DIR
    )

    retriever_data = vectordb.as_retriever(search_kwargs={"k": 5})

    tool = create_retriever_tool(
        retriever=retriever_data,
        name="retrieve_itsm_kb",
        description="Search the Ivanti + BRD knowledge base and return relevant passages with their sources."
    )

    return tool


if __name__ == "__main__":
    main_grounding_data(rebuild=False)
    tool = build_retriever_tool()