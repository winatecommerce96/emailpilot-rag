/**
 * RAG Manager — Audit, Score & Prune documents
 * Lets admins run relevance audits against test queries,
 * review per-document scores, and bulk-prune low-quality docs.
 */

import {
    Icon,
    Button,
    Input,
    Badge,
    Card,
    CardHeader,
    CardTitle,
    CardContent,
    Alert,
    AlertTitle,
    AlertDescription,
    Progress,
    EmptyState,
    Spinner,
} from './ui.jsx';

const { useState, useCallback } = React;

const ORCHESTRATOR_URL = window.RAG_CONFIG?.orchestratorUrl || '';
const SERVICE_URL = window.RAG_CONFIG?.serviceUrl || '';

// Use orchestrator if available, else fall back to service URL
function apiBase() {
    return ORCHESTRATOR_URL || SERVICE_URL;
}

async function apiPost(path, body) {
    const res = await fetch(`${apiBase()}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
        throw new Error(data?.error?.message || data?.detail || `HTTP ${res.status}`);
    }
    return data;
}

// ---------------------------------------------------------------------------
// Score bar — visual indicator for 0-1 relevance score
// ---------------------------------------------------------------------------
function ScoreBar({ score }) {
    const pct = Math.round(score * 100);
    let color = 'bg-red-500';
    if (pct >= 70) color = 'bg-green-500';
    else if (pct >= 50) color = 'bg-yellow-500';
    else if (pct >= 30) color = 'bg-orange-500';

    return (
        <div className="flex items-center gap-2 min-w-[120px]">
            <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
            </div>
            <span className="text-xs font-mono w-10 text-right">{pct}%</span>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export function RAGManager({ clientId, toast }) {
    // Audit state
    const [queries, setQueries] = useState('');
    const [minScore, setMinScore] = useState(0.3);
    const [topK, setTopK] = useState(10);
    const [auditLoading, setAuditLoading] = useState(false);
    const [auditResult, setAuditResult] = useState(null);
    const [auditError, setAuditError] = useState(null);

    // Selection state for prune
    const [selected, setSelected] = useState(new Set());

    // Prune state
    const [pruneLoading, setPruneLoading] = useState(false);
    const [pruneResult, setPruneResult] = useState(null);

    // -----------------------------------------------------------------------
    // Run audit
    // -----------------------------------------------------------------------
    const runAudit = useCallback(async () => {
        if (!clientId) {
            toast.error('Select a client first');
            return;
        }
        const queryList = queries
            .split('\n')
            .map(q => q.trim())
            .filter(Boolean);
        if (queryList.length === 0) {
            toast.error('Enter at least one test query');
            return;
        }

        setAuditLoading(true);
        setAuditError(null);
        setAuditResult(null);
        setSelected(new Set());
        setPruneResult(null);

        try {
            const resp = await apiPost('/api/rag/enhanced/audit', {
                client_id: clientId,
                queries: queryList,
                top_k: topK,
                min_score: minScore,
            });
            const result = resp.data || resp;
            setAuditResult(result);

            // Pre-select low relevance docs
            if (result.low_relevance_docs?.length) {
                setSelected(new Set(result.low_relevance_docs));
            }

            toast.success(
                `Audit complete: ${result.summary?.total_docs || 0} docs scored, ` +
                `${result.summary?.low_relevance_count || 0} flagged`
            );
        } catch (err) {
            setAuditError(err.message);
            toast.error(`Audit failed: ${err.message}`);
        } finally {
            setAuditLoading(false);
        }
    }, [clientId, queries, topK, minScore, toast]);

    // -----------------------------------------------------------------------
    // Toggle selection
    // -----------------------------------------------------------------------
    const toggleSelect = (docId) => {
        setSelected(prev => {
            const next = new Set(prev);
            if (next.has(docId)) next.delete(docId);
            else next.add(docId);
            return next;
        });
    };

    const toggleSelectAll = () => {
        if (!auditResult?.documents) return;
        const allIds = auditResult.documents.map(d => d.doc_id);
        if (selected.size === allIds.length) {
            setSelected(new Set());
        } else {
            setSelected(new Set(allIds));
        }
    };

    // -----------------------------------------------------------------------
    // Prune selected
    // -----------------------------------------------------------------------
    const runPrune = useCallback(async () => {
        if (!clientId || selected.size === 0) return;

        const confirmed = window.confirm(
            `Delete ${selected.size} document${selected.size > 1 ? 's' : ''} and rebuild the vector index?\n\nThis cannot be undone.`
        );
        if (!confirmed) return;

        setPruneLoading(true);
        setPruneResult(null);

        try {
            const resp = await apiPost('/api/rag/enhanced/prune', {
                client_id: clientId,
                doc_ids: Array.from(selected),
                rebuild_index: true,
            });
            const result = resp.data || resp;
            setPruneResult(result);

            // Remove pruned docs from audit result
            if (auditResult) {
                const deletedSet = new Set(result.deleted || []);
                setAuditResult(prev => ({
                    ...prev,
                    documents: prev.documents.filter(d => !deletedSet.has(d.doc_id)),
                    low_relevance_docs: prev.low_relevance_docs.filter(id => !deletedSet.has(id)),
                }));
                setSelected(new Set());
            }

            toast.success(
                `Pruned ${result.deleted_count || 0} docs. ` +
                `Index rebuilt: ${result.vector_index_rebuilt ? 'yes' : 'no'}`
            );
        } catch (err) {
            toast.error(`Prune failed: ${err.message}`);
        } finally {
            setPruneLoading(false);
        }
    }, [clientId, selected, auditResult, toast]);

    // -----------------------------------------------------------------------
    // Render
    // -----------------------------------------------------------------------
    if (!clientId) {
        return (
            <EmptyState
                icon="user-x"
                title="No Client Selected"
                description="Select a client from the dropdown above to audit and manage RAG documents."
            />
        );
    }

    return (
        <div className="space-y-6">
            {/* ---- Audit Controls ---- */}
            <div className="space-y-4">
                <h3 className="text-lg font-semibold flex items-center gap-2">
                    <Icon name="activity" className="h-5 w-5 text-blue-600" />
                    Relevance Audit
                </h3>
                <p className="text-sm text-gray-500">
                    Enter test queries (one per line) to score every document by relevance.
                    Documents that never match above the threshold are flagged for pruning.
                </p>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                    {/* Queries textarea */}
                    <div className="lg:col-span-2">
                        <label className="block text-sm font-medium mb-1">Test Queries</label>
                        <textarea
                            className="w-full h-28 px-3 py-2 text-sm rounded-md border border-input bg-background focus:outline-none focus:ring-2 focus:ring-ring resize-none"
                            placeholder={"What is the brand voice?\nWhat products do they sell?\nWho is the target audience?"}
                            value={queries}
                            onChange={e => setQueries(e.target.value)}
                        />
                    </div>

                    {/* Settings */}
                    <div className="space-y-3">
                        <div>
                            <label className="block text-sm font-medium mb-1">Min Score Threshold</label>
                            <Input
                                type="number"
                                min="0" max="1" step="0.05"
                                value={minScore}
                                onChange={e => setMinScore(parseFloat(e.target.value) || 0)}
                            />
                            <p className="text-xs text-gray-400 mt-1">0-1 range (0.3 = lenient)</p>
                        </div>
                        <div>
                            <label className="block text-sm font-medium mb-1">Top K per query</label>
                            <Input
                                type="number"
                                min="1" max="50"
                                value={topK}
                                onChange={e => setTopK(parseInt(e.target.value) || 10)}
                            />
                        </div>
                    </div>
                </div>

                <div className="flex items-center gap-3">
                    <Button onClick={runAudit} disabled={auditLoading}>
                        {auditLoading ? (
                            <>
                                <svg className="animate-spin h-4 w-4 mr-2" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                </svg>
                                Running Audit...
                            </>
                        ) : (
                            <>
                                <Icon name="search" className="h-4 w-4 mr-2" />
                                Run Audit
                            </>
                        )}
                    </Button>

                    {selected.size > 0 && (
                        <Button
                            variant="destructive"
                            onClick={runPrune}
                            disabled={pruneLoading}
                        >
                            {pruneLoading ? (
                                <>
                                    <svg className="animate-spin h-4 w-4 mr-2" viewBox="0 0 24 24">
                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                    </svg>
                                    Pruning...
                                </>
                            ) : (
                                <>
                                    <Icon name="trash-2" className="h-4 w-4 mr-2" />
                                    Prune {selected.size} doc{selected.size > 1 ? 's' : ''}
                                </>
                            )}
                        </Button>
                    )}
                </div>
            </div>

            {/* ---- Error ---- */}
            {auditError && (
                <Alert variant="destructive">
                    <AlertTitle>Audit Failed</AlertTitle>
                    <AlertDescription>{auditError}</AlertDescription>
                </Alert>
            )}

            {/* ---- Prune Result ---- */}
            {pruneResult && (
                <Alert>
                    <AlertTitle>Prune Complete</AlertTitle>
                    <AlertDescription>
                        Deleted {pruneResult.deleted_count || 0} documents.
                        Docs before: {pruneResult.before_stats?.document_count}, after: {pruneResult.after_stats?.document_count}.
                        {pruneResult.vector_index_rebuilt && ' Vector index rebuilt.'}
                        {pruneResult.failed?.length > 0 && ` ${pruneResult.failed.length} failed.`}
                        {pruneResult.invalid_ids?.length > 0 && ` ${pruneResult.invalid_ids.length} not found.`}
                    </AlertDescription>
                </Alert>
            )}

            {/* ---- Audit Results ---- */}
            {auditResult && (
                <div className="space-y-4">
                    {/* Summary cards */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className="p-4 rounded-lg border border-gray-100 bg-white">
                            <div className="text-2xl font-bold">{auditResult.summary?.total_docs || 0}</div>
                            <div className="text-xs text-gray-500 mt-1">Total Documents</div>
                        </div>
                        <div className="p-4 rounded-lg border border-gray-100 bg-white">
                            <div className="text-2xl font-bold">{auditResult.summary?.docs_scored || 0}</div>
                            <div className="text-xs text-gray-500 mt-1">Docs Matched</div>
                        </div>
                        <div className="p-4 rounded-lg border border-gray-100 bg-white">
                            <div className="text-2xl font-bold">{auditResult.summary?.queries_run || 0}</div>
                            <div className="text-xs text-gray-500 mt-1">Queries Run</div>
                        </div>
                        <div className="p-4 rounded-lg border border-orange-200 bg-orange-50">
                            <div className="text-2xl font-bold text-orange-700">{auditResult.summary?.low_relevance_count || 0}</div>
                            <div className="text-xs text-orange-600 mt-1">Low Relevance</div>
                        </div>
                    </div>

                    {/* Results table */}
                    <div className="border rounded-lg overflow-hidden">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="bg-gray-50 border-b">
                                    <th className="w-10 px-3 py-3 text-left">
                                        <input
                                            type="checkbox"
                                            className="rounded border-gray-300"
                                            checked={auditResult.documents?.length > 0 && selected.size === auditResult.documents.length}
                                            onChange={toggleSelectAll}
                                        />
                                    </th>
                                    <th className="px-3 py-3 text-left font-medium text-gray-600">Document</th>
                                    <th className="px-3 py-3 text-left font-medium text-gray-600 w-20">Chunks</th>
                                    <th className="px-3 py-3 text-left font-medium text-gray-600 w-20">Matched</th>
                                    <th className="px-3 py-3 text-left font-medium text-gray-600 w-36">Avg Score</th>
                                    <th className="px-3 py-3 text-left font-medium text-gray-600 w-36">Best Score</th>
                                    <th className="px-3 py-3 text-left font-medium text-gray-600 w-24">Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {(auditResult.documents || []).map((doc) => {
                                    const isLow = auditResult.low_relevance_docs?.includes(doc.doc_id);
                                    return (
                                        <tr
                                            key={doc.doc_id}
                                            className={`border-b last:border-0 hover:bg-gray-50 transition-colors ${isLow ? 'bg-orange-50/50' : ''}`}
                                        >
                                            <td className="px-3 py-3">
                                                <input
                                                    type="checkbox"
                                                    className="rounded border-gray-300"
                                                    checked={selected.has(doc.doc_id)}
                                                    onChange={() => toggleSelect(doc.doc_id)}
                                                />
                                            </td>
                                            <td className="px-3 py-3">
                                                <div className="font-medium text-gray-900 truncate max-w-[300px]">
                                                    {doc.title || doc.doc_id}
                                                </div>
                                                <div className="text-xs text-gray-400 font-mono truncate">
                                                    {doc.doc_id}
                                                </div>
                                            </td>
                                            <td className="px-3 py-3 text-gray-600">{doc.chunk_count || 0}</td>
                                            <td className="px-3 py-3 text-gray-600">{doc.queries_matched || 0}</td>
                                            <td className="px-3 py-3">
                                                <ScoreBar score={doc.avg_score || 0} />
                                            </td>
                                            <td className="px-3 py-3">
                                                <ScoreBar score={doc.max_score || 0} />
                                            </td>
                                            <td className="px-3 py-3">
                                                {isLow ? (
                                                    <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-orange-100 text-orange-700">
                                                        <Icon name="alert-triangle" className="h-3 w-3" />
                                                        Low
                                                    </span>
                                                ) : doc.queries_matched > 0 ? (
                                                    <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700">
                                                        <Icon name="check" className="h-3 w-3" />
                                                        Good
                                                    </span>
                                                ) : (
                                                    <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-500">
                                                        No hits
                                                    </span>
                                                )}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>

                        {auditResult.documents?.length === 0 && (
                            <div className="p-8 text-center text-gray-500">
                                No documents found for this client.
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
