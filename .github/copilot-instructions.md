# GCP-RAG-VIVADO Project Instructions

## Project Overview
This is a Google Cloud Platform (GCP) based Retrieval-Augmented Generation (RAG) system with VIVADO FPGA acceleration support.

## Tech Stack
- **Language**: Python 3.10+
- **Cloud Platform**: Google Cloud Platform (GCP)
- **AI/ML**: Vertex AI, LangChain
- **Database**: BigQuery, Cloud Storage
- **FPGA**: Xilinx VIVADO integration

## Project Structure
```
GCP-RAG-VIVADO/
├── src/
│   ├── rag/              # RAG pipeline components
│   ├── gcp/              # GCP service integrations
│   ├── fpga/             # VIVADO/FPGA acceleration
│   └── utils/            # Utility functions
├── config/               # Configuration files
├── tests/                # Unit tests
├── docs/                 # Documentation
└── scripts/              # Deployment scripts
```

## Development Guidelines
- Use virtual environment for Python dependencies
- Follow PEP 8 coding standards
- Use type hints for all functions
- Document all public APIs

## GCP Services Used
- Vertex AI for embeddings and LLM
- Cloud Storage for document storage
- BigQuery for vector store
- Cloud Functions for serverless compute

## FPGA Integration
- VIVADO HLS for hardware acceleration
- Custom IP cores for vector operations
- PCIe interface for host communication
