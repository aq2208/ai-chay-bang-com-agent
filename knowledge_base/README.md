# Knowledge Base

This directory manages the static reference documents and the vector database indexing used for RAG-grounded classification, solution matching, and Q&A.

## Directory Structure

- **[docs/](./docs/)**: Contains markdown files defining domain-specific issues, suggested approaches/resolutions, and the classification taxonomy ([taxonomy.md](./docs/taxonomy.md)).
- **[index.py](./index.py)**: Script to parse and index the markdown files into ChromaDB. Rebuilds two collections: `knowledge_base` (solutions) and `taxonomy` (classification grounding).
- **[search.py](./search.py)**: Provides search functions to retrieve relevant solutions and taxonomy hints from the indexed collection.
- **[issues_store.py](./issues_store.py)**: Manages a dynamic, writable collection `issues` that stores grouped issues from pipeline runs, enabling Product Owner Q&A queries.

## Getting Started

To build or refresh the vector database indexes, run:
```bash
python knowledge_base/index.py
```
