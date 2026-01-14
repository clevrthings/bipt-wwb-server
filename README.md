# BIPT → Shure Wireless Workbench Inclusion Lists

This project automatically generates Shure Wireless Workbench (.ils) inclusion lists
based on official BIPT microphone zone documents (Belgium).

## Features
- Nightly check for new BIPT documents
- Automatic .ils generation per quarter
- Keeps current + next quarter available
- Simple web interface for downloads
- Debug/admin page with download & visitor stats
- Designed for Docker & Synology NAS

## Local development (no Docker)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export DATA_DIR=./data
export DEBUG_USER=admin
export DEBUG_PASS=changeme

uvicorn app.main:app --reload --port 8080
