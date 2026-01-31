/**
 * React Hooks for RAG Service Integration
 * Provides state management and data fetching for RAG operations
 */

const { useState, useEffect, useCallback, useRef } = React;

/**
 * Hook for RAG search functionality
 */
export function useRAGSearch(clientId) {
    const [results, setResults] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const search = useCallback(async (query, phase = 'GENERAL', k = 5) => {
        if (!clientId || !query.trim()) {
            setResults([]);
            return [];
        }

        setLoading(true);
        setError(null);

        try {
            const response = await fetch(`${window.RAG_CONFIG?.serviceUrl || ''}/api/rag/search`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({
                    client_id: clientId,
                    query: query,
                    phase: phase,
                    k: k,
                }),
            });

            if (!response.ok) {
                throw new Error(`Search failed: ${response.status}`);
            }

            const data = await response.json();
            setResults(data);
            return data;
        } catch (err) {
            console.error('RAG Search Error:', err);
            setError(err.message);
            setResults([]);
            return [];
        } finally {
            setLoading(false);
        }
    }, [clientId]);

    const clear = useCallback(() => {
        setResults([]);
        setError(null);
    }, []);

    return { results, loading, error, search, clear };
}

/**
 * Hook for document library management
 * Fixed: Proper clientId synchronization with AbortController for cleanup
 */
export function useDocuments(clientId) {
    const [documents, setDocuments] = useState([]);
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [pagination, setPagination] = useState({ page: 1, limit: 20, total: 0 });

    // Use ref to track the current clientId for async operations
    const clientIdRef = useRef(clientId);
    const abortControllerRef = useRef(null);

    const baseUrl = window.RAG_CONFIG?.serviceUrl || '';

    // Update ref when clientId changes
    useEffect(() => {
        clientIdRef.current = clientId;
    }, [clientId]);

    // Core fetch function that uses the passed clientId directly
    const fetchDocumentsForClient = useCallback(async (targetClientId, page = 1, limit = 20, signal) => {
        if (!targetClientId) return null;

        const response = await fetch(
            `${baseUrl}/api/documents/${targetClientId}?page=${page}&limit=${limit}`,
            { signal, credentials: 'include' }
        );

        if (!response.ok) {
            throw new Error(`Failed to fetch documents: ${response.status}`);
        }

        return response.json();
    }, [baseUrl]);

    const fetchStatsForClient = useCallback(async (targetClientId, signal) => {
        if (!targetClientId) return null;

        const response = await fetch(
            `${baseUrl}/api/stats/${targetClientId}`,
            { signal, credentials: 'include' }
        );

        if (response.ok) {
            return response.json();
        }
        return null;
    }, [baseUrl]);

    // Public fetch function that uses current clientId from ref
    const fetchDocuments = useCallback(async (page = 1, limit = 20) => {
        const currentClientId = clientIdRef.current;
        if (!currentClientId) return;

        setLoading(true);
        setError(null);

        try {
            const data = await fetchDocumentsForClient(currentClientId, page, limit);

            // Only update state if clientId hasn't changed during the fetch
            if (clientIdRef.current === currentClientId && data) {
                setDocuments(data.documents || []);
                setPagination({
                    page: data.page || page,
                    limit: data.limit || limit,
                    total: data.total || 0,
                });
            }
        } catch (err) {
            if (err.name !== 'AbortError') {
                console.error('Document Fetch Error:', err);
                if (clientIdRef.current === currentClientId) {
                    setError(err.message);
                }
            }
        } finally {
            if (clientIdRef.current === currentClientId) {
                setLoading(false);
            }
        }
    }, [fetchDocumentsForClient]);

    const fetchStats = useCallback(async () => {
        const currentClientId = clientIdRef.current;
        if (!currentClientId) return;

        try {
            const data = await fetchStatsForClient(currentClientId);
            if (clientIdRef.current === currentClientId && data) {
                setStats(data);
            }
        } catch (err) {
            if (err.name !== 'AbortError') {
                console.error('Stats Fetch Error:', err);
            }
        }
    }, [fetchStatsForClient]);

    const deleteDocument = useCallback(async (docId) => {
        const currentClientId = clientIdRef.current;
        if (!currentClientId) return false;

        try {
            const response = await fetch(
                `${baseUrl}/api/documents/${currentClientId}/${docId}`,
                { method: 'DELETE', credentials: 'include' }
            );

            if (!response.ok) {
                throw new Error('Delete failed');
            }

            // Refresh list using current pagination
            await fetchDocuments(pagination.page, pagination.limit);
            await fetchStats();
            return true;
        } catch (err) {
            setError(err.message);
            return false;
        }
    }, [baseUrl, pagination, fetchDocuments, fetchStats]);

    // Effect that triggers on clientId change - THE CRITICAL FIX
    // Only depends on clientId, not on callback functions
    useEffect(() => {
        // Cancel any in-flight requests
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }

        // Reset state when client changes
        setDocuments([]);
        setStats(null);
        setError(null);
        setPagination({ page: 1, limit: 20, total: 0 });

        if (!clientId) {
            setLoading(false);
            return;
        }

        // Create new abort controller for this request
        const controller = new AbortController();
        abortControllerRef.current = controller;

        const loadClientData = async () => {
            setLoading(true);
            setError(null);

            try {
                // Fetch documents and stats in parallel
                const [docsData, statsData] = await Promise.all([
                    fetchDocumentsForClient(clientId, 1, 20, controller.signal),
                    fetchStatsForClient(clientId, controller.signal)
                ]);

                // Only update if this is still the active request
                if (!controller.signal.aborted) {
                    if (docsData) {
                        setDocuments(docsData.documents || []);
                        setPagination({
                            page: docsData.page || 1,
                            limit: docsData.limit || 20,
                            total: docsData.total || 0,
                        });
                    }
                    if (statsData) {
                        setStats(statsData);
                    }
                }
            } catch (err) {
                if (err.name !== 'AbortError' && !controller.signal.aborted) {
                    console.error('Client Data Load Error:', err);
                    setError(err.message);
                }
            } finally {
                if (!controller.signal.aborted) {
                    setLoading(false);
                }
            }
        };

        loadClientData();

        // Cleanup: abort request if clientId changes or component unmounts
        return () => {
            controller.abort();
        };
    }, [clientId, fetchDocumentsForClient, fetchStatsForClient]);

    const refresh = useCallback(() => {
        fetchDocuments(pagination.page, pagination.limit);
        fetchStats();
    }, [fetchDocuments, fetchStats, pagination]);

    const retry = useCallback(() => {
        setError(null);
        fetchDocuments(1, 20);
        fetchStats();
    }, [fetchDocuments, fetchStats]);

    return {
        documents,
        stats,
        loading,
        error,
        pagination,
        fetchDocuments,
        fetchStats,
        deleteDocument,
        refresh,
        retry,
    };
}

/**
 * Hook for file uploads with progress tracking
 */
export function useUpload(clientId) {
    const [uploading, setUploading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [error, setError] = useState(null);
    const [results, setResults] = useState([]);

    const baseUrl = window.RAG_CONFIG?.serviceUrl || '';

    const uploadFiles = useCallback(async (files, metadata = {}) => {
        if (!clientId || files.length === 0) return [];

        setUploading(true);
        setProgress(0);
        setError(null);
        setResults([]);

        const uploadResults = [];
        const totalFiles = files.length;

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const formData = new FormData();
            formData.append('file', file);

            if (metadata.title) formData.append('title', metadata.title || file.name);
            // Only send source_type if not using auto-categorize OR if source_type is explicitly set
            if (metadata.source_type && !metadata.auto_categorize) {
                formData.append('source_type', metadata.source_type);
            }
            if (metadata.tags) formData.append('tags', metadata.tags);
            // NEW: Send auto_categorize flag (default true if not specified)
            formData.append('auto_categorize', metadata.auto_categorize !== false ? 'true' : 'false');

            try {
                const response = await fetch(`${baseUrl}/api/documents/${clientId}/upload`, {
                    method: 'POST',
                    body: formData,
                    credentials: 'include',
                });

                const result = await response.json();
                uploadResults.push({
                    file: file.name,
                    success: response.ok,
                    data: result,
                    error: response.ok ? null : result.detail,
                    // Include categorization info if present
                    categorization: result.categorization || null,
                });
            } catch (err) {
                uploadResults.push({
                    file: file.name,
                    success: false,
                    error: err.message,
                });
            }

            setProgress(Math.round(((i + 1) / totalFiles) * 100));
        }

        setResults(uploadResults);
        setUploading(false);
        return uploadResults;
    }, [clientId, baseUrl]);

    const uploadText = useCallback(async (content, metadata = {}) => {
        if (!clientId || !content.trim()) return null;

        setUploading(true);
        setError(null);

        try {
            const formData = new FormData();
            formData.append('content', content);
            formData.append('title', metadata.title || 'Text Document');
            // Only send source_type if not using auto-categorize
            if (metadata.source_type && !metadata.auto_categorize) {
                formData.append('source_type', metadata.source_type);
            }
            formData.append('tags', metadata.tags || '');
            // NEW: Send auto_categorize flag (default true if not specified)
            formData.append('auto_categorize', metadata.auto_categorize !== false ? 'true' : 'false');

            const response = await fetch(`${baseUrl}/api/documents/${clientId}/text`, {
                method: 'POST',
                body: formData,
                credentials: 'include',
            });

            const result = await response.json();
            setUploading(false);

            if (!response.ok) {
                setError(result.detail || 'Upload failed');
                return null;
            }

            return result;
        } catch (err) {
            setError(err.message);
            setUploading(false);
            return null;
        }
    }, [clientId, baseUrl]);

    const uploadUrl = useCallback(async (url, metadata = {}) => {
        // URL upload not implemented in standalone mode
        setError('URL upload not available in standalone mode');
        return null;
    }, [clientId, baseUrl]);

    const reset = useCallback(() => {
        setProgress(0);
        setError(null);
        setResults([]);
    }, []);

    return {
        uploading,
        progress,
        error,
        results,
        uploadFiles,
        uploadText,
        uploadUrl,
        reset,
    };
}

/**
 * Hook for job status tracking
 */
export function useJobs(orchestratorUrl = '') {
    const [jobs, setJobs] = useState(new Map());
    const [loading, setLoading] = useState(false);
    const pollingRef = useRef(null);

    const baseUrl = orchestratorUrl || window.RAG_CONFIG?.orchestratorUrl || '';

    const addJob = useCallback((jobId, initialStatus = {}) => {
        setJobs(prev => {
            const next = new Map(prev);
            next.set(jobId, {
                id: jobId,
                status: 'QUEUED',
                progress: 0,
                ...initialStatus,
                addedAt: Date.now(),
            });
            return next;
        });
    }, []);

    const updateJob = useCallback((jobId, updates) => {
        setJobs(prev => {
            const next = new Map(prev);
            const current = next.get(jobId) || { id: jobId };
            next.set(jobId, { ...current, ...updates });
            return next;
        });
    }, []);

    const removeJob = useCallback((jobId) => {
        setJobs(prev => {
            const next = new Map(prev);
            next.delete(jobId);
            return next;
        });
    }, []);

    const pollJob = useCallback(async (jobId) => {
        try {
            const response = await fetch(`${baseUrl}/api/rag/enhanced/jobs/${jobId}/status`, { credentials: 'include' });
            if (response.ok) {
                const data = await response.json();
                updateJob(jobId, data.data || data);
                return data.data || data;
            }
        } catch (err) {
            console.error('Job poll error:', err);
        }
        return null;
    }, [baseUrl, updateJob]);

    const startPolling = useCallback((interval = 2000) => {
        if (pollingRef.current) return;

        pollingRef.current = setInterval(async () => {
            const activeJobs = Array.from(jobs.entries())
                .filter(([_, job]) => !['INDEXED', 'ERROR', 'CANCELLED'].includes(job.status));

            for (const [jobId] of activeJobs) {
                await pollJob(jobId);
            }
        }, interval);
    }, [jobs, pollJob]);

    const stopPolling = useCallback(() => {
        if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
        }
    }, []);

    // Cleanup on unmount
    useEffect(() => {
        return () => stopPolling();
    }, [stopPolling]);

    // Auto-start polling when jobs are added
    useEffect(() => {
        const hasActiveJobs = Array.from(jobs.values()).some(
            job => !['INDEXED', 'ERROR', 'CANCELLED'].includes(job.status)
        );

        if (hasActiveJobs && !pollingRef.current) {
            startPolling();
        } else if (!hasActiveJobs && pollingRef.current) {
            stopPolling();
        }
    }, [jobs, startPolling, stopPolling]);

    return {
        jobs: Array.from(jobs.values()),
        jobsMap: jobs,
        loading,
        addJob,
        updateJob,
        removeJob,
        pollJob,
        startPolling,
        stopPolling,
        activeCount: Array.from(jobs.values()).filter(
            j => !['INDEXED', 'ERROR', 'CANCELLED'].includes(j.status)
        ).length,
        completedCount: Array.from(jobs.values()).filter(
            j => j.status === 'INDEXED'
        ).length,
    };
}

/**
 * Hook for toast notifications
 */
export function useToast() {
    const [toasts, setToasts] = useState([]);

    const addToast = useCallback((message, type = 'info', duration = 5000) => {
        const id = Date.now();
        setToasts(prev => [...prev, { id, message, type, duration }]);

        if (duration > 0) {
            setTimeout(() => {
                setToasts(prev => prev.filter(t => t.id !== id));
            }, duration);
        }

        return id;
    }, []);

    const removeToast = useCallback((id) => {
        setToasts(prev => prev.filter(t => t.id !== id));
    }, []);

    const success = useCallback((message, duration) => addToast(message, 'success', duration), [addToast]);
    const error = useCallback((message, duration) => addToast(message, 'error', duration), [addToast]);
    const warning = useCallback((message, duration) => addToast(message, 'warning', duration), [addToast]);
    const info = useCallback((message, duration) => addToast(message, 'info', duration), [addToast]);

    return { toasts, addToast, removeToast, success, error, warning, info };
}

export default {
    useRAGSearch,
    useDocuments,
    useUpload,
    useJobs,
    useToast,
};
