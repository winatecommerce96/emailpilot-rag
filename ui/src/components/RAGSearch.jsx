/**
 * Intelligence Search Component
 * For testing semantic search against the Intelligence Hub
 */

import { Icon } from './ui.jsx';

const { useState } = React;

const PHASES = [
    { value: 'GENERAL', label: 'General', description: 'Search all documents' },
    { value: 'STRATEGY', label: 'Strategy', description: 'Brand voice + past campaigns' },
    { value: 'BRIEF', label: 'Brief', description: 'Product specs + brand voice' },
    { value: 'VISUAL', label: 'Visual', description: 'Visual assets only' },
];

export function RAGSearch({
    clientId,
    onSearch,
    results = [],
    loading = false,
    error = null,
}) {
    const [query, setQuery] = useState('');
    const [phase, setPhase] = useState('GENERAL');
    const [topK, setTopK] = useState(5);

    const handleSearch = (e) => {
        e.preventDefault();
        if (query.trim() && clientId) {
            onSearch?.(query, phase, topK);
        }
    };

    const formatScore = (score) => {
        if (typeof score !== 'number') return 'N/A';
        return `${(score * 100).toFixed(0)}%`;
    };

    const getScoreColor = (score) => {
        if (score >= 0.8) return 'text-success';
        if (score >= 0.5) return 'text-yellow-600';
        return 'text-muted-foreground';
    };

    return (
        <div className="space-y-6">
            {/* Search Form */}
            <form onSubmit={handleSearch} className="space-y-4">
                {/* Query Input */}
                <div>
                    <label className="block text-sm font-medium mb-2">Search Query</label>
                    <div className="relative">
                        <input
                            type="text"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            placeholder="e.g., What is the brand voice for email campaigns?"
                            className="w-full h-12 pl-4 pr-12 rounded-lg border border-input bg-background text-base focus:outline-none focus:ring-2 focus:ring-ring"
                            disabled={!clientId}
                        />
                        <button
                            type="submit"
                            disabled={!query.trim() || !clientId || loading}
                            className="absolute right-2 top-1/2 -translate-y-1/2 h-8 w-8 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
                        >
                            {loading ? (
                                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                </svg>
                            ) : (
                                <Icon name="search" className="h-4 w-4" />
                            )}
                        </button>
                    </div>
                </div>

                {/* Options */}
                <div className="flex flex-wrap gap-4">
                    {/* Phase Selector */}
                    <div className="flex-1 min-w-[200px]">
                        <label className="block text-sm font-medium mb-2">Search Phase</label>
                        <select
                            value={phase}
                            onChange={(e) => setPhase(e.target.value)}
                            className="w-full h-10 px-3 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                        >
                            {PHASES.map((p) => (
                                <option key={p.value} value={p.value}>
                                    {p.label} - {p.description}
                                </option>
                            ))}
                        </select>
                    </div>

                    {/* Top K */}
                    <div className="w-32">
                        <label className="block text-sm font-medium mb-2">Results</label>
                        <select
                            value={topK}
                            onChange={(e) => setTopK(parseInt(e.target.value))}
                            className="w-full h-10 px-3 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                        >
                            {[3, 5, 10, 15, 20].map((k) => (
                                <option key={k} value={k}>Top {k}</option>
                            ))}
                        </select>
                    </div>
                </div>
            </form>

            {/* Error State */}
            {error && (
                <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
                    <div className="flex items-start gap-3">
                        <Icon name="alert-circle" className="h-5 w-5 text-destructive mt-0.5" />
                        <div>
                            <p className="font-medium text-destructive">Search Error</p>
                            <p className="text-sm text-destructive/80 mt-1">{error}</p>
                        </div>
                    </div>
                </div>
            )}

            {/* No Client Selected */}
            {!clientId && (
                <div className="rounded-lg border border-yellow-500/50 bg-yellow-50 p-4">
                    <div className="flex items-start gap-3">
                        <Icon name="alert-triangle" className="h-5 w-5 text-yellow-600 mt-0.5" />
                        <div>
                            <p className="font-medium text-yellow-700">No Client Selected</p>
                            <p className="text-sm text-yellow-600 mt-1">Please select a client to test intelligence search.</p>
                        </div>
                    </div>
                </div>
            )}

            {/* Results */}
            {results.length > 0 && (
                <div className="space-y-4">
                    <div className="flex items-center justify-between">
                        <h3 className="font-medium">Search Results</h3>
                        <span className="text-sm text-muted-foreground">{results.length} results</span>
                    </div>

                    <div className="space-y-3">
                        {results.map((result, index) => (
                            <div
                                key={index}
                                className="rounded-lg border bg-card p-4 hover:shadow-sm transition-all"
                            >
                                {/* Header */}
                                <div className="flex items-start justify-between gap-4 mb-3">
                                    <div className="flex items-center gap-2">
                                        <span className="flex items-center justify-center h-6 w-6 rounded-full bg-primary/10 text-primary text-xs font-medium">
                                            {index + 1}
                                        </span>
                                        <span className="text-sm font-medium">
                                            {result.metadata?.title || 'Untitled Document'}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <span className={`text-sm font-medium ${getScoreColor(result.relevance_score)}`}>
                                            {formatScore(result.relevance_score)}
                                        </span>
                                        <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                                            {result.metadata?.category || 'general'}
                                        </span>
                                    </div>
                                </div>

                                {/* Content */}
                                <div className="bg-muted/50 rounded-md p-3">
                                    <p className="text-sm text-foreground/80 whitespace-pre-wrap">
                                        {result.content?.length > 500
                                            ? `${result.content.slice(0, 500)}...`
                                            : result.content || 'No content available'}
                                    </p>
                                </div>

                                {/* Metadata */}
                                {result.metadata && (
                                    <div className="flex flex-wrap gap-2 mt-3">
                                        {result.metadata.source && (
                                            <span className="text-xs text-muted-foreground">
                                                Source: {result.metadata.source}
                                            </span>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Empty State (after search) */}
            {!loading && results.length === 0 && query && clientId && (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                    <div className="rounded-full bg-muted p-4 mb-4">
                        <Icon name="search-x" className="h-8 w-8 text-muted-foreground" />
                    </div>
                    <h3 className="text-lg font-semibold">No results found</h3>
                    <p className="text-sm text-muted-foreground mt-1 max-w-sm">
                        Try adjusting your search query or changing the search phase.
                    </p>
                </div>
            )}

            {/* Initial State */}
            {!loading && results.length === 0 && !query && clientId && (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                    <div className="rounded-full bg-muted p-4 mb-4">
                        <Icon name="sparkles" className="h-8 w-8 text-muted-foreground" />
                    </div>
                    <h3 className="text-lg font-semibold">Test Intelligence Hub</h3>
                    <p className="text-sm text-muted-foreground mt-1 max-w-sm">
                        Enter a query above to search your indexed documents with AI-powered semantic search.
                    </p>
                </div>
            )}
        </div>
    );
}

export default RAGSearch;
