**Ivanti ITSM Request Offering Configuration – AI-Assisted Builder**

This project automatically extracts a Request Offering (RO) from a Business Requirements Document (BRD) and produces Ivanti-ready JSON files.



**Output Files**
File	Description
workflow_logic.json	Workflow graph (blocks, links, notifications, and status transitions).
form.json	Internal authoring structure with {"template": ..., "fields": [...]}. Optionally exported in Ivanti naming {"CatalogItem": ..., "FormFields": [...]} using transform_bundle().

The system uses a retrieval-augmented generation (RAG) pattern built on:

A Chroma vector store (local knowledge base)

OpenAI embeddings

Lightweight validation and normalization logic



**Environment & Requirements**

Keep the same dependency versions used during project development:

langchain>=0.2.15
langchain-core>=0.2.30
langchain-community>=0.2.10
langchain-openai>=0.1.7
langchain-chroma>=0.1.2
langchain-text-splitters>=0.2.2
chromadb>=0.5.3
pypdf>=4.2.0
docx2txt>=0.8
openai>=1.40.0
python-dotenv>=1.0.0

Installation
python -m venv venv
source venv/bin/activate           # Windows: venv\Scripts\activate
pip install -r requirements.txt


Note: Add your OpenAI key in .env:

OPENAI_API_KEY=sk-...

Knowledge Base (KB) Ingestion

You only need to ingest data once (or when the BRD changes).
The Chroma vector database is saved at kb/chroma_ivanti/.

main_grounding_data(rebuild=False) → reuses the existing KB (no re-embedding)

main_grounding_data(rebuild=True) → rebuilds from documents

Why Chroma + MMR

text-embedding-3-small → balances speed and cost

search_type="mmr" → Maximal Marginal Relevance improves diversity and reduces duplicate results from the BRD




**Core Pipeline (Extractor)**

The logic is handled inside create_structure_json(...).
Here’s the simplified flow:

Load retriever from kb/chroma_ivanti/.

Query specific buckets:

offering → Catalog item details

fields → Form field definitions

workflow → Workflow structure and transitions

Gap check:
If the first retrieval doesn’t have enough context, it performs targeted follow-ups using an approved list of queries (avoids random retries).
The follow-up logic is logged in _followups_meta.json.

LLM extraction (structured JSON):

OFFERING_SYS / OFFERING_USER → Offering JSON

FIELDS_SYS / FIELDS_USER → Form JSON

WORKFLOW_SYS / WORKFLOW_USER → Workflow JSON

Normalization:

minimal_normalize_offering() → fixes data types and records missing_fields (e.g., if BRD lacks description/category).

Field cleanup (sequence order, deduped options, expressions consistency).

Tenant placeholders

Some values (e.g., templates or group IDs) are tenant-specific, so they’re left as placeholders:

"<GROUP_REC_ID_IT_KNOWLEDGE>"
"<TEMPLATE_ON_APPROVAL>"


These are later replaced via tenant_config.json.



**Validation & Export**

Two main scripts handle validation and export.

A) End-to-End extraction
python data_structure_agent.py


Generates:

structured/form.json
structured/workflow_logic.json
structured/_followups_meta.json

B) Validate and re-export
python main.py
