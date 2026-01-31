/**
 * RAG Service API Client
 * Handles all communication with the RAG microservice
 *
 * Production: https://rag-service-xyz.run.app
 * Development: http://localhost:8001
 */

// Configuration
const RAG_SERVICE_URL = window.RAG_CONFIG?.serviceUrl || '';
const API_TIMEOUT = 30000; // 30 seconds

// Request phases for intelligent context retrieval
export const RAGPhase = {
    STRATEGY: 'STRATEGY',   // Brand voice + past campaigns
    BRIEF: 'BRIEF',         // Product specs + brand voice
    VISUAL: 'VISUAL',       // Visual assets only
    GENERAL: 'GENERAL',     // Search everything
};

// Document source types
export const SourceType = {
    BRAND_GUIDELINES: 'brand_guidelines',
    MARKETING_STRATEGY: 'marketing_strategy',
    PRODUCT_INFO: 'product_info',
    CAMPAIGN_HISTORY: 'campaign_history',
    VISUAL_ASSET: 'visual_asset',
    GENERAL: 'general',
};

/**
 * Base API client with error handling and retries
 */
class APIClient {
    constructor(baseUrl) {
        this.baseUrl = baseUrl;
        this.retryCount = 3;
        this.retryDelay = 1000;
    }

    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), options.timeout || API_TIMEOUT);

        const config = {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
            signal: controller.signal,
        };

        let lastError;
        for (let attempt = 0; attempt < this.retryCount; attempt++) {
            try {
                const response = await fetch(url, config);
                clearTimeout(timeoutId);

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new APIError(
                        errorData.detail || `HTTP ${response.status}`,
                        response.status,
                        errorData
                    );
                }

                return await response.json();
            } catch (error) {
                lastError = error;
                if (error.name === 'AbortError') {
                    throw new APIError('Request timeout', 408);
                }
                if (attempt < this.retryCount - 1 && this.shouldRetry(error)) {
                    await this.delay(this.retryDelay * Math.pow(2, attempt));
                    continue;
                }
                throw error instanceof APIError ? error : new APIError(error.message, 0);
            }
        }
        throw lastError;
    }

    shouldRetry(error) {
        // Retry on network errors or 5xx server errors
        return !error.status || error.status >= 500;
    }

    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    get(endpoint, options = {}) {
        return this.request(endpoint, { ...options, method: 'GET' });
    }

    post(endpoint, body, options = {}) {
        return this.request(endpoint, {
            ...options,
            method: 'POST',
            body: JSON.stringify(body),
        });
    }

    put(endpoint, body, options = {}) {
        return this.request(endpoint, {
            ...options,
            method: 'PUT',
            body: JSON.stringify(body),
        });
    }

    delete(endpoint, options = {}) {
        return this.request(endpoint, { ...options, method: 'DELETE' });
    }
}

/**
 * Custom API Error class
 */
export class APIError extends Error {
    constructor(message, status, data = {}) {
        super(message);
        this.name = 'APIError';
        this.status = status;
        this.data = data;
    }
}

/**
 * Client Management
 * For fetching orchestrator clients (single source of truth)
 */
export class ClientService {
    constructor() {
        this.client = new APIClient(RAG_SERVICE_URL);
    }

    /**
     * Fetch all live clients from orchestrator
     * @param {boolean} includeInactive - Include inactive clients
     */
    async getClients(includeInactive = false) {
        const params = includeInactive ? '?include_inactive=true' : '';
        return this.client.get(`/api/orchestrator/clients${params}`);
    }

    /**
     * Fetch clients (backwards compatible - uses orchestrator with fallback)
     */
    async list() {
        return this.client.get('/api/clients');
    }

    /**
     * Get client statistics
     */
    async getStats(clientId) {
        return this.client.get(`/api/stats/${clientId}`);
    }
}

/**
 * RAG Search Client
 * For querying the Vertex AI-powered search
 */
export class RAGSearchClient {
    constructor() {
        this.client = new APIClient(RAG_SERVICE_URL);
    }

    /**
     * Perform a phase-aware semantic search
     * @param {string} clientId - Client identifier for data isolation
     * @param {string} query - Search query text
     * @param {string} phase - Workflow phase (STRATEGY, BRIEF, VISUAL, GENERAL)
     * @param {number} k - Number of results (1-20)
     */
    async search(clientId, query, phase = RAGPhase.GENERAL, k = 5) {
        try {
            const results = await this.client.post('/api/rag/search', {
                client_id: clientId,
                query: query,
                phase: phase,
                k: Math.min(Math.max(k, 1), 20),
            });
            return results;
        } catch (error) {
            console.error('RAG Search Error:', error);
            return []; // Fail safe: return empty list, don't crash app
        }
    }

    /**
     * Health check
     */
    async healthCheck() {
        return this.client.get('/health');
    }
}

/**
 * Document Management Client
 * For CRUD operations on RAG documents
 */
export class DocumentClient {
    constructor(orchestratorUrl = '') {
        // If orchestrator URL is provided, use enhanced RAG endpoints
        this.client = new APIClient(orchestratorUrl || RAG_SERVICE_URL);
        this.useEnhanced = !!orchestratorUrl;
    }

    /**
     * List documents for a client
     */
    async list(clientId, page = 1, limit = 20) {
        const endpoint = this.useEnhanced
            ? `/api/rag/enhanced/list/${clientId}?page=${page}&limit=${limit}`
            : `/api/documents/${clientId}`;
        return this.client.get(endpoint);
    }

    /**
     * Get document by ID
     */
    async get(clientId, docId) {
        const endpoint = this.useEnhanced
            ? `/api/rag/enhanced/docs/${clientId}/${docId}`
            : `/api/documents/${clientId}/${docId}`;
        return this.client.get(endpoint);
    }

    /**
     * Delete document
     */
    async delete(clientId, docId) {
        const endpoint = this.useEnhanced
            ? `/api/rag/enhanced/docs/${clientId}/${docId}`
            : `/api/documents/${clientId}/${docId}`;
        return this.client.delete(endpoint);
    }

    /**
     * Update document
     */
    async update(clientId, docId, data) {
        const endpoint = this.useEnhanced
            ? `/api/rag/enhanced/docs/${clientId}/${docId}`
            : `/api/documents/${clientId}/${docId}`;
        return this.client.put(endpoint, data);
    }

    /**
     * Get client statistics
     */
    async getStats(clientId) {
        const endpoint = this.useEnhanced
            ? `/api/rag/enhanced/stats/${clientId}`
            : `/api/stats/${clientId}`;
        return this.client.get(endpoint);
    }

    /**
     * Export document
     */
    async export(clientId, docId, format = 'json') {
        const endpoint = this.useEnhanced
            ? `/api/rag/enhanced/docs/${clientId}/${docId}/export?format=${format}`
            : `/api/documents/${clientId}/${docId}/export?format=${format}`;
        return this.client.get(endpoint);
    }
}

/**
 * File Upload Client
 * Handles multi-file uploads with progress tracking
 */
export class UploadClient {
    constructor(orchestratorUrl = '') {
        this.baseUrl = orchestratorUrl || RAG_SERVICE_URL;
    }

    /**
     * Upload files with progress callback
     * @param {string} clientId - Client ID
     * @param {File[]} files - Array of files to upload
     * @param {object} metadata - Document metadata
     * @param {function} onProgress - Progress callback (0-100)
     * @returns {Promise<object[]>} - Array of job responses
     */
    async uploadFiles(clientId, files, metadata = {}, onProgress = () => {}) {
        const results = [];
        const totalFiles = files.length;

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const formData = new FormData();
            formData.append('file', file);
            formData.append('client_id', clientId);

            if (metadata.title) formData.append('title', metadata.title || file.name);
            if (metadata.source_type) formData.append('source_type', metadata.source_type);
            if (metadata.tags) formData.append('tags', metadata.tags);

            try {
                const response = await fetch(`${this.baseUrl}/api/rag/enhanced/ingest/file`, {
                    method: 'POST',
                    body: formData,
                });

                if (!response.ok) {
                    const error = await response.json().catch(() => ({}));
                    throw new APIError(error.detail || 'Upload failed', response.status);
                }

                const result = await response.json();
                results.push({ file: file.name, success: true, data: result });
            } catch (error) {
                results.push({ file: file.name, success: false, error: error.message });
            }

            // Report progress
            onProgress(Math.round(((i + 1) / totalFiles) * 100));
        }

        return results;
    }

    /**
     * Upload text content
     */
    async uploadText(clientId, content, metadata = {}) {
        const response = await fetch(`${this.baseUrl}/api/rag/enhanced/ingest/text`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                client_id: clientId,
                content: content,
                title: metadata.title || 'Text Document',
                source_type: metadata.source_type || 'general',
                tags: metadata.tags || [],
            }),
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new APIError(error.detail || 'Upload failed', response.status);
        }

        return response.json();
    }

    /**
     * Ingest from URL
     */
    async uploadUrl(clientId, url, metadata = {}) {
        const response = await fetch(`${this.baseUrl}/api/rag/enhanced/ingest/url`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                client_id: clientId,
                url: url,
                title: metadata.title || url,
                source_type: metadata.source_type || 'general',
                tags: metadata.tags || [],
            }),
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new APIError(error.detail || 'URL ingestion failed', response.status);
        }

        return response.json();
    }
}

/**
 * Job Tracking Client
 * For monitoring async ingestion jobs
 */
export class JobClient {
    constructor(orchestratorUrl = '') {
        this.client = new APIClient(orchestratorUrl || RAG_SERVICE_URL);
    }

    /**
     * Get job status
     */
    async getStatus(jobId) {
        return this.client.get(`/api/rag/enhanced/jobs/${jobId}/status`);
    }

    /**
     * List all jobs
     */
    async list(status = null) {
        const params = status ? `?status=${status}` : '';
        return this.client.get(`/api/rag/enhanced/jobs${params}`);
    }

    /**
     * Cancel a job
     */
    async cancel(jobId) {
        return this.client.delete(`/api/rag/enhanced/jobs/${jobId}`);
    }

    /**
     * Poll job until completion
     * @param {string} jobId - Job ID to poll
     * @param {function} onUpdate - Status update callback
     * @param {number} interval - Polling interval in ms
     * @param {number} timeout - Maximum wait time in ms
     */
    async pollUntilComplete(jobId, onUpdate = () => {}, interval = 2000, timeout = 300000) {
        const startTime = Date.now();

        while (Date.now() - startTime < timeout) {
            const status = await this.getStatus(jobId);
            onUpdate(status);

            if (['INDEXED', 'ERROR', 'CANCELLED'].includes(status.status)) {
                return status;
            }

            await new Promise(resolve => setTimeout(resolve, interval));
        }

        throw new APIError('Job polling timeout', 408);
    }
}

// Export singleton instances for convenience
export const clientService = new ClientService();
export const ragSearch = new RAGSearchClient();
export const documents = new DocumentClient();
export const upload = new UploadClient();
export const jobs = new JobClient();

// Default export for module import
export default {
    ClientService,
    RAGSearchClient,
    DocumentClient,
    UploadClient,
    JobClient,
    RAGPhase,
    SourceType,
    APIError,
    clientService,
    ragSearch,
    documents,
    upload,
    jobs,
};
