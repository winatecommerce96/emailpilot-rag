# EmailPilot RAG Service

This project is a FastAPI-based microservice called "EmailPilot RAG Service". It provides Retrieval-Augmented Generation (RAG) capabilities, document management, and semantic search using Google Vertex AI Discovery Engine. The service is designed to be used within the "EmailPilot" ecosystem.

### Key Features

*   **FastAPI Backend**: The core of the service is a Python-based FastAPI application.
*   **Vertex AI Integration**: It uses Google Vertex AI Discovery Engine for semantic search and document storage.
*   **RAG Implementation**: The service implements a Retrieval-Augmented Generation pipeline.
*   **Document Management**: It supports uploading, managing, and searching documents in various formats (PDF, DOCX, text).
*   **Google Docs Integration**: Users can import documents directly from their Google Docs.
*   **Image Repository Pipeline**: An automated pipeline syncs images from Google Drive, analyzes them with Gemini Vision, and indexes them in Vertex AI.
*   **React Frontend**: A React-based user interface is provided for document management and interacting with the service.
*   **Authentication**: The service supports JWT-based authentication using Clerk.

### Building and Running

**Prerequisites:**

*   Python 3.11+
*   Google Cloud Project with Vertex AI Discovery Engine enabled
*   Service account with appropriate permissions

**Installation:**

```bash
# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

**Environment Variables:**

Create a `.env` file in the root of the project with the following variables:

```
# GCP Configuration
GCP_PROJECT_ID=your-gcp-project-id
GCP_LOCATION=us
VERTEX_DATA_STORE_ID=your-vertex-data-store-id

# Orchestrator Integration
ORCHESTRATOR_URL=https://emailpilot-orchestrator-url
INTERNAL_SERVICE_KEY=your-internal-service-key

# Google Docs OAuth (Optional)
GOOGLE_OAUTH_CLIENT_ID=your-google-oauth-client-id
GOOGLE_OAUTH_CLIENT_SECRET=your-google-oauth-client-secret
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8003/api/google/callback

# Clerk Authentication (Optional)
CLERK_FRONTEND_API=your-clerk-frontend-api
CLERK_PUBLISHABLE_KEY=your-clerk-publishable-key
GLOBAL_AUTH_ENABLED=true

# Image Repository Pipeline (Optional)
GEMINI_API_KEY=your-gemini-api-key
```

**Running the Application:**

```bash
# Start the FastAPI server
uvicorn app.main:app --port 8003 --reload
```

The application will be available at `http://localhost:8003`.

### Development Conventions

*   **Backend**: The backend is written in Python using the FastAPI framework. It follows a modular structure, with services, models, and API routes separated into different files.
*   **Frontend**: The frontend is a React application built with `esbuild`.
*   **Dependencies**: Python dependencies are managed with `pip` and `requirements.txt`. Frontend dependencies are managed with `npm` and `package.json`.
*   **Authentication**: Authentication is handled via JWTs provided by Clerk.
*   **Testing**: The `README.md` does not specify a testing framework, but there is a `test_auth.py` file, which suggests that tests are written using a framework like `pytest`.

### Project Structure

```
RAG/
├── app/
│   ├── main.py              # FastAPI application
│   ├── auth.py              # Clerk JWT authentication
│   ├── models/
│   │   └── schemas.py       # Pydantic models
│   └── services/
│       ├── vertex_search.py # Vertex AI Discovery Engine client
│       └── google_docs.py   # Google Docs OAuth service
├── pipelines/
│   └── image-repository/    # Image indexing pipeline
│       ├── api/routes.py    # FastAPI routes
│       ├── core/            # Pipeline components
│       └── config/          # Settings and folder mappings
├── ui/                      # React frontend
├── data/                    # Local data storage
├── requirements.txt
├── Dockerfile
└── README.md
```

## Clerk Authentication

This service uses Clerk for JWT validation:
- **Development**: `current-stork-99.clerk.accounts.dev` (test keys `pk_test_*`)
- **Production**: GCP Secret Manager (live keys `pk_live_*`)
- **Canonical env vars**: `CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`
- The service now receives `CLERK_SECRET_KEY` from the deployment script for proper JWT validation
