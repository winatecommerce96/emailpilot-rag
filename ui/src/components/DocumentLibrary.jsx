/**
 * Document Library Component
 * Lists, searches, and manages RAG documents
 * Enhanced with loading overlays, error handling, and retry mechanism
 */

import { Icon } from './ui.jsx';

const { useState, useCallback, useMemo } = React;

// Category options for filtering
const CATEGORY_OPTIONS = [
    { value: '', label: 'All Categories' },
    { value: 'brand_voice', label: 'Brand Voice' },
    { value: 'brand_guidelines', label: 'Brand Guidelines' },
    { value: 'content_pillars', label: 'Content Pillars' },
    { value: 'marketing_strategy', label: 'Marketing Strategy' },
    { value: 'product', label: 'Product' },
    { value: 'target_audience', label: 'Target Audience' },
    { value: 'past_campaign', label: 'Past Campaign' },
    { value: 'seasonal_themes', label: 'Seasonal Themes' },
    { value: 'general', label: 'General' },
];

export function DocumentLibrary({
    documents = [],
    loading = false,
    error = null,
    pagination = { page: 1, limit: 20, total: 0 },
    onPageChange,
    onDelete,
    onView,
    onExport,
    onRefresh,
    onRetry,
    onSwitchToUpload,
}) {
    const [search, setSearch] = useState('');
    const [categoryFilter, setCategoryFilter] = useState('');
    const [deleteConfirm, setDeleteConfirm] = useState(null);
    const [deleting, setDeleting] = useState(false);

    const filteredDocs = documents.filter(doc => {
        const searchLower = search.toLowerCase();
        const matchesSearch = (
            doc.title?.toLowerCase().includes(searchLower) ||
            doc.source_type?.toLowerCase().includes(searchLower) ||
            doc.tags?.some(t => t.toLowerCase().includes(searchLower))
        );
        const matchesCategory = !categoryFilter || doc.source_type === categoryFilter;
        return matchesSearch && matchesCategory;
    });

    const formatDate = (dateStr) => {
        if (!dateStr) return 'Unknown';
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
        });
    };

    const formatSize = (chars) => {
        if (!chars) return 'Unknown';
        if (chars < 1000) return `${chars} chars`;
        return `${(chars / 1000).toFixed(1)}k chars`;
    };

    const getSourceTypeColor = (type) => {
        const colors = {
            brand_voice: 'bg-indigo-100 text-indigo-700',
            brand_guidelines: 'bg-purple-100 text-purple-700',
            content_pillars: 'bg-cyan-100 text-cyan-700',
            marketing_strategy: 'bg-blue-100 text-blue-700',
            product: 'bg-green-100 text-green-700',
            target_audience: 'bg-amber-100 text-amber-700',
            past_campaign: 'bg-orange-100 text-orange-700',
            seasonal_themes: 'bg-rose-100 text-rose-700',
            general: 'bg-gray-100 text-gray-700',
        };
        return colors[type] || colors.general;
    };

    const handleDelete = async (doc) => {
        setDeleting(true);
        try {
            await onDelete?.(doc.id);
            setDeleteConfirm(null);
        } finally {
            setDeleting(false);
        }
    };

    const totalPages = Math.ceil(pagination.total / pagination.limit);

    return (
        <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-3 flex-1">
                    <div className="relative flex-1 max-w-sm">
                        <Icon name="search" className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <input
                            type="text"
                            placeholder="Search documents..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="w-full h-10 pl-10 pr-4 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                        />
                    </div>
                    <select
                        value={categoryFilter}
                        onChange={(e) => setCategoryFilter(e.target.value)}
                        className="h-10 px-3 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                    >
                        {CATEGORY_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                                {opt.label}
                            </option>
                        ))}
                    </select>
                </div>
                <button
                    onClick={onRefresh}
                    disabled={loading}
                    className="h-10 px-4 rounded-md border border-input bg-background hover:bg-accent transition-colors disabled:opacity-50"
                >
                    <Icon name="refresh-cw" className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                </button>
            </div>

            {/* Stats */}
            <div className="flex items-center gap-4 text-sm text-muted-foreground">
                <span>{pagination.total} documents</span>
                <span>•</span>
                <span>Page {pagination.page} of {totalPages || 1}</span>
            </div>

            {/* Error State */}
            {error && (
                <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 mb-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <Icon name="alert-circle" className="h-5 w-5 text-destructive flex-shrink-0" />
                            <div>
                                <p className="text-sm font-medium text-destructive">Failed to load documents</p>
                                <p className="text-xs text-muted-foreground mt-0.5">{error}</p>
                            </div>
                        </div>
                        <button
                            onClick={onRetry || onRefresh}
                            className="h-8 px-3 rounded-md bg-destructive/10 hover:bg-destructive/20 text-destructive text-sm font-medium transition-colors"
                        >
                            Retry
                        </button>
                    </div>
                </div>
            )}

            {/* Document List */}
            <div className="relative">
                {/* Loading Overlay - shows during refresh */}
                {loading && documents.length > 0 && (
                    <div className="absolute inset-0 bg-background/80 flex items-center justify-center z-10 rounded-lg">
                        <div className="flex items-center gap-2 bg-card px-4 py-2 rounded-full shadow-sm border">
                            <svg className="animate-spin h-4 w-4 text-primary" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                            </svg>
                            <span className="text-sm text-muted-foreground">Refreshing...</span>
                        </div>
                    </div>
                )}

            {loading && documents.length === 0 && !error ? (
                <div className="space-y-3">
                    <div className="flex items-center gap-2 mb-2">
                        <svg className="animate-spin h-4 w-4 text-primary" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                        <span className="text-sm text-muted-foreground">Loading documents...</span>
                    </div>
                    {[1, 2, 3].map(i => (
                        <div key={i} className="skeleton h-20 rounded-lg" />
                    ))}
                </div>
            ) : !loading && !error && filteredDocs.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                    <div className="rounded-full bg-muted p-4 mb-4">
                        <Icon name={(search || categoryFilter) ? "search-x" : "folder-plus"} className="h-8 w-8 text-muted-foreground" />
                    </div>
                    <h3 className="text-lg font-semibold">
                        {(search || categoryFilter) ? 'No matching documents' : 'No documents yet'}
                    </h3>
                    <p className="text-sm text-muted-foreground mt-1 mb-4">
                        {(search || categoryFilter)
                            ? 'Try a different search term or clear your filters'
                            : 'Get started by uploading your first document for this client'}
                    </p>
                    {!search && !categoryFilter && onSwitchToUpload && (
                        <button
                            onClick={onSwitchToUpload}
                            className="h-10 px-4 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 flex items-center gap-2"
                        >
                            <Icon name="upload" className="h-4 w-4" />
                            Upload Your First Document
                        </button>
                    )}
                    {(search || categoryFilter) && (
                        <button
                            onClick={() => { setSearch(''); setCategoryFilter(''); }}
                            className="h-10 px-4 rounded-md border border-input bg-background hover:bg-accent text-sm font-medium"
                        >
                            Clear Filters
                        </button>
                    )}
                </div>
            ) : !error && (
                <div className="space-y-2">
                    {filteredDocs.map((doc) => (
                        <div
                            key={doc.id}
                            className="group flex items-start gap-4 p-4 rounded-lg border bg-card hover:shadow-sm transition-all"
                        >
                            {/* Icon */}
                            <div className="rounded-lg bg-muted p-2">
                                <Icon name="file-text" className="h-5 w-5 text-muted-foreground" />
                            </div>

                            {/* Content */}
                            <div className="flex-1 min-w-0">
                                <div className="flex items-start justify-between gap-2">
                                    <h4 className="font-medium truncate">{doc.title || 'Untitled'}</h4>
                                    <span className={`text-xs px-2 py-0.5 rounded-full ${getSourceTypeColor(doc.source_type)}`}>
                                        {doc.source_type?.replace(/_/g, ' ') || 'general'}
                                    </span>
                                </div>

                                <div className="flex items-center gap-3 mt-1 text-sm text-muted-foreground">
                                    <span>{formatDate(doc.created_at)}</span>
                                    <span>•</span>
                                    <span>{formatSize(doc.size)}</span>
                                </div>

                                {doc.tags && doc.tags.length > 0 && (
                                    <div className="flex flex-wrap gap-1 mt-2">
                                        {doc.tags.slice(0, 5).map((tag, i) => (
                                            <span
                                                key={i}
                                                className="text-xs px-2 py-0.5 rounded-full bg-secondary text-secondary-foreground"
                                            >
                                                {tag}
                                            </span>
                                        ))}
                                        {doc.tags.length > 5 && (
                                            <span className="text-xs text-muted-foreground">
                                                +{doc.tags.length - 5} more
                                            </span>
                                        )}
                                    </div>
                                )}
                            </div>

                            {/* Actions */}
                            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                <button
                                    onClick={() => onView?.(doc)}
                                    className="p-2 rounded-md hover:bg-muted"
                                    title="View document"
                                >
                                    <Icon name="eye" className="h-4 w-4 text-muted-foreground" />
                                </button>
                                <button
                                    onClick={() => onExport?.(doc, 'json')}
                                    className="p-2 rounded-md hover:bg-muted"
                                    title="Export"
                                >
                                    <Icon name="download" className="h-4 w-4 text-muted-foreground" />
                                </button>
                                <button
                                    onClick={() => setDeleteConfirm(doc)}
                                    className="p-2 rounded-md hover:bg-destructive/10"
                                    title="Delete"
                                >
                                    <Icon name="trash-2" className="h-4 w-4 text-destructive" />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
            </div> {/* End of relative wrapper */}

            {/* Pagination */}
            {totalPages > 1 && (
                <div className="flex items-center justify-center gap-2">
                    <button
                        onClick={() => onPageChange?.(pagination.page - 1)}
                        disabled={pagination.page <= 1}
                        className="h-8 w-8 rounded-md border border-input bg-background hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <Icon name="chevron-left" className="h-4 w-4 mx-auto" />
                    </button>

                    {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                        let page;
                        if (totalPages <= 5) {
                            page = i + 1;
                        } else if (pagination.page <= 3) {
                            page = i + 1;
                        } else if (pagination.page >= totalPages - 2) {
                            page = totalPages - 4 + i;
                        } else {
                            page = pagination.page - 2 + i;
                        }
                        return (
                            <button
                                key={page}
                                onClick={() => onPageChange?.(page)}
                                className={`h-8 w-8 rounded-md text-sm font-medium ${
                                    page === pagination.page
                                        ? 'bg-primary text-primary-foreground'
                                        : 'border border-input bg-background hover:bg-accent'
                                }`}
                            >
                                {page}
                            </button>
                        );
                    })}

                    <button
                        onClick={() => onPageChange?.(pagination.page + 1)}
                        disabled={pagination.page >= totalPages}
                        className="h-8 w-8 rounded-md border border-input bg-background hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <Icon name="chevron-right" className="h-4 w-4 mx-auto" />
                    </button>
                </div>
            )}

            {/* Delete Confirmation Dialog */}
            {deleteConfirm && (
                <div className="fixed inset-0 z-50">
                    <div
                        className="fixed inset-0 bg-black/80"
                        onClick={() => !deleting && setDeleteConfirm(null)}
                    />
                    <div className="fixed inset-0 flex items-center justify-center p-4">
                        <div className="bg-background rounded-lg shadow-lg max-w-md w-full p-6 animate-fade-in">
                            <div className="flex items-center gap-3 mb-4">
                                <div className="rounded-full bg-destructive/10 p-2">
                                    <Icon name="alert-triangle" className="h-5 w-5 text-destructive" />
                                </div>
                                <h3 className="text-lg font-semibold">Delete Document</h3>
                            </div>
                            <p className="text-sm text-muted-foreground mb-6">
                                Are you sure you want to delete <strong>"{deleteConfirm.title}"</strong>?
                                This action cannot be undone.
                            </p>
                            <div className="flex justify-end gap-2">
                                <button
                                    onClick={() => setDeleteConfirm(null)}
                                    disabled={deleting}
                                    className="h-10 px-4 rounded-md border border-input bg-background hover:bg-accent disabled:opacity-50"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={() => handleDelete(deleteConfirm)}
                                    disabled={deleting}
                                    className="h-10 px-4 rounded-md bg-destructive text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50"
                                >
                                    {deleting ? (
                                        <span className="flex items-center gap-2">
                                            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                            </svg>
                                            Deleting...
                                        </span>
                                    ) : 'Delete'}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export default DocumentLibrary;
