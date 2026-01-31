/**
 * RAG Document Manager - Main Application
 * A modern UI for managing RAG documents and testing semantic search
 */

// Import components (these will be bundled by esbuild)
import {
    Icon,
    Button,
    Input,
    Select,
    Card,
    CardHeader,
    CardTitle,
    CardDescription,
    CardContent,
    Badge,
    Tabs,
    TabsList,
    TabsTrigger,
    TabsContent,
    Progress,
    Alert,
    AlertTitle,
    AlertDescription,
    ToastContainer,
    EmptyState,
    Spinner,
} from './components/ui.jsx';
import { FileUpload } from './components/FileUpload.jsx';
import { DocumentLibrary } from './components/DocumentLibrary.jsx';
import { RAGSearch } from './components/RAGSearch.jsx';
import { UserManager } from './components/UserManager.jsx';
import { useRAGSearch, useDocuments, useUpload, useToast } from './hooks/useRAG.js';

const { useState, useEffect, useCallback } = React;

// ============================================================================
// CONFIGURATION (set in index.html, defaults here as fallback)
// ============================================================================
window.RAG_CONFIG = window.RAG_CONFIG || {
    serviceUrl: window.location.origin,
    orchestratorUrl: '',
};

// Source type options - aligned with LLM categorizer
const SOURCE_TYPES = [
    { value: 'brand_voice', label: 'Brand Voice' },
    { value: 'brand_guidelines', label: 'Brand Guidelines' },
    { value: 'content_pillars', label: 'Content Pillars' },
    { value: 'marketing_strategy', label: 'Marketing Strategy' },
    { value: 'product', label: 'Product Catalog' },
    { value: 'target_audience', label: 'Target Audience' },
    { value: 'past_campaign', label: 'Campaign History' },
    { value: 'seasonal_themes', label: 'Seasonal Themes' },
    { value: 'general', label: 'General' },
];

// ============================================================================
// CLIENT SELECTOR COMPONENT (Enhanced with status/industry badges)
// ============================================================================
function ClientSelector({ value, onChange, clients, loading, onRefresh }) {
    const [isOpen, setIsOpen] = useState(false);
    const selectedClient = clients.find(c => c.client_id === value);

    // Close dropdown when clicking outside
    useEffect(() => {
        const handleClickOutside = (e) => {
            if (!e.target.closest('.client-selector-dropdown')) {
                setIsOpen(false);
            }
        };
        document.addEventListener('click', handleClickOutside);
        return () => document.removeEventListener('click', handleClickOutside);
    }, []);

    const getStatusColor = (status) => {
        switch (status?.toUpperCase()) {
            case 'LIVE': return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400';
            case 'ONBOARDING': return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400';
            case 'INACTIVE': return 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400';
            default: return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400';
        }
    };

    return (
        <div className="relative client-selector-dropdown">
            <button
                onClick={(e) => { e.stopPropagation(); setIsOpen(!isOpen); }}
                disabled={loading}
                className="w-full h-10 pl-3 pr-10 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring flex items-center gap-2 text-left"
            >
                <Icon name={loading ? "refresh-cw" : "building-2"} className={`h-4 w-4 text-muted-foreground flex-shrink-0 ${loading ? 'animate-spin' : ''}`} />
                {loading ? (
                    <span className="text-muted-foreground">Loading clients...</span>
                ) : selectedClient ? (
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                        <span className="truncate">{selectedClient.name}</span>
                        {selectedClient.status && (
                            <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded ${getStatusColor(selectedClient.status)}`}>
                                {selectedClient.status}
                            </span>
                        )}
                    </div>
                ) : (
                    <span className="text-muted-foreground">Select a client...</span>
                )}
                <Icon name="chevron-down" className={`absolute right-3 h-4 w-4 text-muted-foreground transition-transform ${isOpen ? 'rotate-180' : ''}`} />
            </button>

            {isOpen && (
                <div className="absolute z-50 mt-1 w-full min-w-[320px] max-h-[400px] overflow-auto rounded-md border border-input bg-background shadow-lg">
                    <div className="p-2 border-b border-input bg-muted/50">
                        <div className="flex items-center justify-between">
                            <span className="text-xs font-medium text-muted-foreground">
                                {clients.length} Live Client{clients.length !== 1 ? 's' : ''}
                            </span>
                            <button
                                onClick={(e) => { e.stopPropagation(); onRefresh(); }}
                                disabled={loading}
                                className="p-1 hover:bg-accent rounded"
                                title="Refresh clients"
                            >
                                <Icon name="refresh-cw" className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
                            </button>
                        </div>
                    </div>
                    <div className="py-1">
                        {clients.length === 0 ? (
                            <div className="px-3 py-4 text-center text-sm text-muted-foreground">
                                {loading ? 'Loading clients...' : 'No clients available'}
                            </div>
                        ) : (
                            clients.map((client) => (
                                <button
                                    key={client.client_id}
                                    onClick={(e) => { e.stopPropagation(); onChange(client.client_id); setIsOpen(false); }}
                                    className={`w-full px-3 py-2 text-left hover:bg-accent flex items-start gap-3 ${value === client.client_id ? 'bg-accent' : ''}`}
                                >
                                    <div className="flex-shrink-0 mt-0.5">
                                        <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
                                            <span className="text-xs font-semibold text-primary">
                                                {(client.name || client.client_id).substring(0, 2).toUpperCase()}
                                            </span>
                                        </div>
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2">
                                            <span className="font-medium text-sm truncate">{client.name || client.client_id}</span>
                                            {client.status && (
                                                <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded flex-shrink-0 ${getStatusColor(client.status)}`}>
                                                    {client.status}
                                                </span>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-2 mt-0.5">
                                            {client.industry && (
                                                <span className="text-xs text-muted-foreground">{client.industry}</span>
                                            )}
                                            {client.document_count > 0 && (
                                                <span className="text-xs text-muted-foreground">
                                                    • {client.document_count} doc{client.document_count !== 1 ? 's' : ''}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    {value === client.client_id && (
                                        <Icon name="check" className="h-4 w-4 text-primary flex-shrink-0 mt-1" />
                                    )}
                                </button>
                            ))
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

// ============================================================================
// MAIN APP COMPONENT
// ============================================================================
function App() {
    // State
    const [activeTab, setActiveTab] = useState('upload');
    const [selectedClient, setSelectedClient] = useState('');
    const [clients, setClients] = useState([]);
    const [clientsLoading, setClientsLoading] = useState(false);

    // Upload metadata
    const [metadata, setMetadata] = useState({
        title: '',
        source_type: 'general',
        tags: '',
        auto_categorize: true,  // NEW: AI auto-categorization enabled by default
    });

    // Last upload categorization results (for display)
    const [lastCategorization, setLastCategorization] = useState(null);

    // Document viewer state
    const [viewingDocument, setViewingDocument] = useState(null);
    const [documentContent, setDocumentContent] = useState(null);
    const [documentLoading, setDocumentLoading] = useState(false);

    // Hooks
    const toast = useToast();
    const search = useRAGSearch(selectedClient);
    const docs = useDocuments(selectedClient);
    const upload = useUpload(selectedClient);

    // Fetch clients from API - no toast dependency to avoid infinite loop
    const fetchClients = useCallback(async () => {
        setClientsLoading(true);
        try {
            const response = await fetch(`${window.RAG_CONFIG?.serviceUrl || ''}/api/clients`);
            if (response.ok) {
                const data = await response.json();
                setClients(data.clients || []);
            } else {
                console.error('Failed to fetch clients:', response.status);
            }
        } catch (err) {
            console.error('Failed to fetch clients:', err);
        } finally {
            setClientsLoading(false);
        }
    }, []); // Empty deps - only create once

    // Handle client selection with feedback
    const handleClientChange = useCallback((clientId) => {
        setSelectedClient(clientId);
        const client = clients.find(c => c.client_id === clientId);
        if (client) {
            toast.success(`Switched to ${client.name}`);
        }
    }, [clients, toast]);

    // Initialize - fetch clients on mount only
    useEffect(() => {
        fetchClients();
    }, []); // Empty deps - run once on mount

    // Handle file upload
    const handleUpload = useCallback(async (files) => {
        if (!selectedClient) {
            toast.error('Please select a client first');
            return;
        }

        setLastCategorization(null);
        const results = await upload.uploadFiles(files, metadata);

        // Show results
        const successCount = results.filter(r => r.success).length;
        const failCount = results.filter(r => !r.success).length;

        if (successCount > 0) {
            // Check for AI categorization results
            const aiCategorized = results.filter(r => r.categorization?.method === 'llm');
            if (aiCategorized.length > 0) {
                const cat = aiCategorized[0].categorization;
                setLastCategorization(cat);
                toast.success(`${successCount} file(s) uploaded! AI categorized as: ${cat.category}`);
            } else {
                toast.success(`${successCount} file(s) uploaded successfully`);
            }
        }
        if (failCount > 0) {
            toast.error(`${failCount} file(s) failed to upload`);
        }

        // Refresh documents
        docs.refresh();
    }, [selectedClient, metadata, upload, toast, docs]);

    // Handle text upload
    const handleTextUpload = useCallback(async (content) => {
        if (!selectedClient) {
            toast.error('Please select a client first');
            return;
        }

        setLastCategorization(null);
        const result = await upload.uploadText(content, metadata);
        if (result) {
            // Check for AI categorization
            if (result.categorization?.method === 'llm') {
                setLastCategorization(result.categorization);
                toast.success(`Text uploaded! AI categorized as: ${result.categorization.category}`);
            } else {
                toast.success('Text content uploaded successfully');
            }
            docs.refresh();
        } else {
            toast.error(upload.error || 'Failed to upload text');
        }
    }, [selectedClient, metadata, upload, toast, docs]);

    // Handle document view - fetch full content and show in modal
    const handleViewDocument = useCallback(async (doc) => {
        setViewingDocument(doc);
        setDocumentContent(null);
        setDocumentLoading(true);

        try {
            const response = await fetch(
                `${window.RAG_CONFIG?.serviceUrl || ''}/api/documents/${selectedClient}/${doc.id}`
            );
            if (response.ok) {
                const data = await response.json();
                setDocumentContent(data);
            } else {
                const errorData = await response.json();
                toast.error(errorData.detail || 'Failed to load document');
                setViewingDocument(null);
            }
        } catch (err) {
            console.error('Failed to fetch document:', err);
            toast.error('Failed to load document content');
            setViewingDocument(null);
        } finally {
            setDocumentLoading(false);
        }
    }, [selectedClient, toast]);

    // Close document viewer
    const handleCloseViewer = useCallback(() => {
        setViewingDocument(null);
        setDocumentContent(null);
    }, []);

    // Handle document export
    const handleExportDocument = useCallback(async (doc, format) => {
        toast.info(`Exporting ${doc.title} as ${format}...`);
        // Implement export logic
    }, [toast]);

    // Handle search
    const handleSearch = useCallback((query, phase, k) => {
        search.search(query, phase, k);
    }, [search]);

    return (
        <div className="bg-background">
            {/* Controls Bar */}
            <div className="bg-white border-b border-gray-200 px-6 py-4">
                <div className="max-w-6xl mx-auto flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        {/* Client Selector */}
                        <div className="w-72">
                            <ClientSelector
                                value={selectedClient}
                                onChange={handleClientChange}
                                clients={clients}
                                loading={clientsLoading}
                                onRefresh={fetchClients}
                            />
                        </div>

                        {/* Health Indicator */}
                        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-green-50 text-green-700 text-sm border border-green-200">
                            <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
                            <span className="font-medium">Connected</span>
                        </div>
                    </div>

                    {/* Settings */}
                    <button
                        onClick={() => setActiveTab('user')}
                        className={`p-2 rounded-md transition-colors ${activeTab === 'user' ? 'bg-blue-50 text-blue-600' : 'hover:bg-gray-100 text-gray-600'}`}
                        title="User Manager & Settings"
                    >
                        <Icon name="settings" className="h-5 w-5" />
                    </button>
                </div>
            </div>

            {/* Main Content */}
            <main className="p-8">
                <div className="max-w-6xl mx-auto">
                    {/* Stats Overview - 3 column grid like figma-feedback.html */}
                    {selectedClient && docs.stats && (
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                            <div className="ep-card ep-shadow-none bg-white p-6 rounded-xl border border-gray-100">
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Documents</span>
                                    <div className="p-2 bg-blue-50 rounded-lg">
                                        <Icon name="file-text" className="h-5 w-5 text-blue-600" />
                                    </div>
                                </div>
                                <div className="text-3xl font-black text-gray-900">{docs.stats.document_count || 0}</div>
                                <p className="text-xs text-gray-400 mt-1">Total documents indexed</p>
                            </div>
                            <div className="ep-card ep-shadow-none bg-white p-6 rounded-xl border border-gray-100">
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Characters</span>
                                    <div className="p-2 bg-purple-50 rounded-lg">
                                        <Icon name="text" className="h-5 w-5 text-purple-600" />
                                    </div>
                                </div>
                                <div className="text-3xl font-black text-gray-900">{((docs.stats.total_characters || 0) / 1000).toFixed(1)}k</div>
                                <p className="text-xs text-gray-400 mt-1">Total content size</p>
                            </div>
                            <div className="ep-card ep-shadow-none bg-white p-6 rounded-xl border border-gray-100">
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Vector Status</span>
                                    <div className={`p-2 rounded-lg ${docs.stats.vector_enabled ? 'bg-green-50' : 'bg-gray-50'}`}>
                                        <Icon name="database" className={`h-5 w-5 ${docs.stats.vector_enabled ? 'text-green-600' : 'text-gray-400'}`} />
                                    </div>
                                </div>
                                <div className="text-3xl font-black text-gray-900">{docs.stats.vector_enabled ? 'Active' : 'Inactive'}</div>
                                <p className="text-xs text-gray-400 mt-1">Semantic search {docs.stats.vector_enabled ? 'enabled' : 'disabled'}</p>
                            </div>
                        </div>
                    )}

                    {/* Main Panel */}
                    <div className="bg-white rounded-xl border border-gray-100 p-6">
                        <Tabs value={activeTab} onValueChange={setActiveTab}>
                            <TabsList className="mb-6">
                                <TabsTrigger value="upload">
                                    <Icon name="upload-cloud" className="h-4 w-4 mr-2" />
                                    Upload
                                </TabsTrigger>
                                <TabsTrigger value="library">
                                    <Icon name="library" className="h-4 w-4 mr-2" />
                                    Library
                                </TabsTrigger>
                                <TabsTrigger value="search">
                                    <Icon name="sparkles" className="h-4 w-4 mr-2" />
                                    Search
                                </TabsTrigger>
                                <TabsTrigger value="grading">
                                    <Icon name="bar-chart-3" className="h-4 w-4 mr-2" />
                                    Intelligence Grade
                                </TabsTrigger>
                                <TabsTrigger value="user">
                                    <Icon name="settings" className="h-4 w-4 mr-2" />
                                    Settings
                                </TabsTrigger>
                            </TabsList>
                                
                                                                    {/* Upload Tab */}
                                    <TabsContent value="upload">
                                        {!selectedClient ? (
                                            <EmptyState
                                                icon="user-x"
                                                title="No Client Selected"
                                                description="Please select a client from the dropdown above to start uploading documents."
                                            />
                                        ) : (
                                            <div className="space-y-6">
                                                {/* AI Categorization Banner */}
                                                <div className={`rounded-lg p-4 border ${metadata.auto_categorize ? 'bg-primary/5 border-primary/20' : 'bg-muted border-muted'}`}>
                                                    <div className="flex items-center justify-between">
                                                        <div className="flex items-center gap-3">
                                                            <div className={`rounded-full p-2 ${metadata.auto_categorize ? 'bg-primary/10' : 'bg-muted'}`}>
                                                                <Icon name="sparkles" className={`h-5 w-5 ${metadata.auto_categorize ? 'text-primary' : 'text-muted-foreground'}`} />
                                                            </div>
                                                            <div>
                                                                <h4 className="text-sm font-medium">AI Auto-Categorization</h4>
                                                                <p className="text-xs text-muted-foreground">
                                                                    {metadata.auto_categorize
                                                                        ? 'Claude will analyze content and assign the best category + keywords'
                                                                        : 'Using manual category selection'}
                                                                </p>
                                                            </div>
                                                        </div>
                                                        <button
                                                            onClick={() => setMetadata(m => ({ ...m, auto_categorize: !m.auto_categorize }))}
                                                            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${metadata.auto_categorize ? 'bg-primary' : 'bg-muted'}`}
                                                        >
                                                            <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${metadata.auto_categorize ? 'translate-x-6' : 'translate-x-1'}`} />
                                                        </button>
                                                    </div>
                                                </div>

                                                {/* Last Categorization Result */}
                                                {lastCategorization && (
                                                    <div className="rounded-lg p-4 bg-success/10 border border-success/20">
                                                        <div className="flex items-start gap-3">
                                                            <Icon name="check-circle" className="h-5 w-5 text-success mt-0.5" />
                                                            <div className="flex-1">
                                                                <h4 className="text-sm font-medium text-success">AI Categorization Result</h4>
                                                                <div className="mt-2 space-y-1">
                                                                    <p className="text-sm">
                                                                        <span className="text-muted-foreground">Category:</span>{' '}
                                                                        <span className="font-medium capitalize">{lastCategorization.category?.replace(/_/g, ' ')}</span>
                                                                    </p>
                                                                    <p className="text-sm">
                                                                        <span className="text-muted-foreground">Confidence:</span>{' '}
                                                                        <span className="font-medium">{Math.round((lastCategorization.confidence || 0) * 100)}%</span>
                                                                    </p>
                                                                    {lastCategorization.keywords?.length > 0 && (
                                                                        <div className="mt-2">
                                                                            <span className="text-xs text-muted-foreground">Keywords:</span>
                                                                            <div className="flex flex-wrap gap-1 mt-1">
                                                                                {lastCategorization.keywords.map((kw, i) => (
                                                                                    <span key={i} className="text-xs px-2 py-0.5 bg-muted rounded-full">
                                                                                        {kw}
                                                                                    </span>
                                                                                ))}
                                                                            </div>
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            </div>
                                                            <button
                                                                onClick={() => setLastCategorization(null)}
                                                                className="p-1 hover:bg-muted rounded"
                                                            >
                                                                <Icon name="x" className="h-4 w-4 text-muted-foreground" />
                                                            </button>
                                                        </div>
                                                    </div>
                                                )}

                                                {/* Metadata Form */}
                                                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                                    <div>
                                                        <label className="block text-sm font-medium mb-2">Document Title</label>
                                                        <Input
                                                            value={metadata.title}
                                                            onChange={(e) => setMetadata(m => ({ ...m, title: e.target.value }))}
                                                            placeholder="Enter title..."
                                                        />
                                                    </div>
                                                    <div>
                                                        <label className="block text-sm font-medium mb-2">
                                                            Source Type
                                                            {metadata.auto_categorize && (
                                                                <span className="ml-2 text-xs text-primary font-normal">(AI will override)</span>
                                                            )}
                                                        </label>
                                                        <Select
                                                            value={metadata.source_type}
                                                            onChange={(e) => setMetadata(m => ({ ...m, source_type: e.target.value }))}
                                                            disabled={metadata.auto_categorize}
                                                            className={metadata.auto_categorize ? 'opacity-50' : ''}
                                                        >
                                                            {SOURCE_TYPES.map((type) => (
                                                                <option key={type.value} value={type.value}>
                                                                    {type.label}
                                                                </option>
                                                            ))}
                                                        </Select>
                                                    </div>
                                                    <div>
                                                        <label className="block text-sm font-medium mb-2">Tags</label>
                                                        <Input
                                                            value={metadata.tags}
                                                            onChange={(e) => setMetadata(m => ({ ...m, tags: e.target.value }))}
                                                            placeholder={metadata.auto_categorize ? "AI will generate keywords" : "tag1, tag2, tag3"}
                                                        />
                                                    </div>
                                                </div>

                                                {/* File Upload */}
                                                <FileUpload
                                                    onFilesSelected={(files) => console.log('Selected:', files.length)}
                                                    onUpload={handleUpload}
                                                    uploading={upload.uploading}
                                                    progress={upload.progress}
                                                    maxFiles={10}
                                                />

                                                {/* Text Input Alternative */}
                                                <div className="border-t pt-6">
                                                    <h4 className="text-sm font-medium mb-3">Or paste text content directly</h4>
                                                    <TextContentUpload
                                                        onUpload={handleTextUpload}
                                                        uploading={upload.uploading}
                                                    />
                                                </div>
                                            </div>
                                        )}
                                    </TabsContent>

                                    {/* Library Tab */}
                                    <TabsContent value="library">
                                        {!selectedClient ? (
                                            <EmptyState
                                                icon="user-x"
                                                title="No Client Selected"
                                                description="Please select a client from the dropdown above to browse documents."
                                            />
                                        ) : (
                                            <DocumentLibrary
                                                documents={docs.documents}
                                                loading={docs.loading}
                                                error={docs.error}
                                                pagination={docs.pagination}
                                                onPageChange={(page) => docs.fetchDocuments(page)}
                                                onDelete={docs.deleteDocument}
                                                onView={handleViewDocument}
                                                onExport={handleExportDocument}
                                                onRefresh={docs.refresh}
                                                onRetry={docs.retry}
                                                onSwitchToUpload={() => setActiveTab('upload')}
                                            />
                                        )}
                                    </TabsContent>

                                    {/* Search Tab */}
                                    <TabsContent value="search">
                                        <RAGSearch
                                            clientId={selectedClient}
                                            results={search.results}
                                            loading={search.loading}
                                            error={search.error}
                                            onSearch={handleSearch}
                                        />
                                    </TabsContent>

                            {/* Intelligence Grading Tab */}
                            <TabsContent value="grading">
                                <IntelligenceGrading
                                    clientId={selectedClient}
                                    toast={toast}
                                />
                            </TabsContent>

                            {/* User Manager Tab */}
                            <TabsContent value="user">
                                <UserManager clientId={selectedClient} />
                            </TabsContent>
                        </Tabs>
                    </div>
                </div>
            </main>

            {/* Toast Container */}
            <ToastContainer toasts={toast.toasts} onRemove={toast.removeToast} />

            {/* Document Viewer Modal */}
            {viewingDocument && (
                <div className="fixed inset-0 z-50">
                    <div
                        className="fixed inset-0 bg-black/80"
                        onClick={handleCloseViewer}
                    />
                    <div className="fixed inset-0 flex items-center justify-center p-4">
                        <div className="bg-background rounded-lg shadow-lg max-w-4xl w-full max-h-[90vh] flex flex-col animate-fade-in">
                            {/* Header */}
                            <div className="flex items-center justify-between p-4 border-b">
                                <div className="flex items-center gap-3 min-w-0">
                                    <div className="rounded-lg bg-muted p-2">
                                        <Icon name="file-text" className="h-5 w-5 text-muted-foreground" />
                                    </div>
                                    <div className="min-w-0">
                                        <h3 className="text-lg font-semibold truncate">
                                            {viewingDocument.title || 'Untitled Document'}
                                        </h3>
                                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                            <span className="capitalize">
                                                {viewingDocument.source_type?.replace(/_/g, ' ') || 'general'}
                                            </span>
                                            {documentContent?.size && (
                                                <>
                                                    <span>•</span>
                                                    <span>{documentContent.size.toLocaleString()} characters</span>
                                                </>
                                            )}
                                        </div>
                                    </div>
                                </div>
                                <button
                                    onClick={handleCloseViewer}
                                    className="p-2 rounded-md hover:bg-muted"
                                >
                                    <Icon name="x" className="h-5 w-5" />
                                </button>
                            </div>

                            {/* Content */}
                            <div className="flex-1 overflow-auto p-4">
                                {documentLoading ? (
                                    <div className="flex items-center justify-center py-12">
                                        <div className="flex items-center gap-3">
                                            <svg className="animate-spin h-5 w-5 text-primary" viewBox="0 0 24 24">
                                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                            </svg>
                                            <span className="text-muted-foreground">Loading document content...</span>
                                        </div>
                                    </div>
                                ) : documentContent?.content ? (
                                    <div className="bg-muted/30 rounded-lg p-4">
                                        <pre className="whitespace-pre-wrap text-sm font-mono leading-relaxed">
                                            {documentContent.content}
                                        </pre>
                                    </div>
                                ) : (
                                    <div className="flex items-center justify-center py-12 text-muted-foreground">
                                        No content available
                                    </div>
                                )}
                            </div>

                            {/* Footer */}
                            <div className="flex items-center justify-between p-4 border-t bg-muted/30">
                                <div className="text-xs text-muted-foreground">
                                    {documentContent?.source && (
                                        <span>Source: {documentContent.source}</span>
                                    )}
                                </div>
                                <div className="flex items-center gap-2">
                                    <button
                                        onClick={() => {
                                            if (documentContent?.content) {
                                                navigator.clipboard.writeText(documentContent.content);
                                                toast.success('Content copied to clipboard');
                                            }
                                        }}
                                        disabled={!documentContent?.content}
                                        className="h-9 px-4 rounded-md border border-input bg-background hover:bg-accent text-sm font-medium disabled:opacity-50"
                                    >
                                        Copy Content
                                    </button>
                                    <button
                                        onClick={handleCloseViewer}
                                        className="h-9 px-4 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 text-sm font-medium"
                                    >
                                        Close
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

// ============================================================================
// INTELLIGENCE GRADING COMPONENT
// ============================================================================
function IntelligenceGrading({ clientId, toast }) {
    const [loading, setLoading] = useState(false);
    const [quickLoading, setQuickLoading] = useState(false);
    const [grade, setGrade] = useState(null);
    const [error, setError] = useState(null);

    // Run full intelligence grading
    const runFullGrading = async () => {
        if (!clientId) {
            toast.error('Please select a client first');
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const response = await fetch(
                `${window.RAG_CONFIG?.serviceUrl || ''}/api/intelligence/grade/${clientId}`
            );

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to grade intelligence');
            }

            const data = await response.json();
            setGrade(data);
            toast.success(`Intelligence Grade: ${data.overall_grade} (${data.overall_score}%)`);
        } catch (err) {
            console.error('Intelligence grading failed:', err);
            setError(err.message);
            toast.error(err.message || 'Failed to analyze intelligence');
        } finally {
            setLoading(false);
        }
    };

    // Run quick assessment (faster, keyword-based)
    const runQuickAssessment = async () => {
        if (!clientId) {
            toast.error('Please select a client first');
            return;
        }

        setQuickLoading(true);
        setError(null);

        try {
            const response = await fetch(
                `${window.RAG_CONFIG?.serviceUrl || ''}/api/intelligence/quick-assessment/${clientId}`
            );

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to assess intelligence');
            }

            const data = await response.json();
            setGrade({
                ...data,
                overall_grade: data.estimated_grade,
                overall_score: data.estimated_score,
                is_quick_assessment: true
            });
            toast.info(`Quick Assessment: ${data.estimated_grade} (${data.estimated_score}%)`);
        } catch (err) {
            console.error('Quick assessment failed:', err);
            setError(err.message);
            toast.error(err.message || 'Failed to assess intelligence');
        } finally {
            setQuickLoading(false);
        }
    };

    // Get grade color
    const getGradeColor = (gradeStr) => {
        switch (gradeStr) {
            case 'A': return 'text-green-600 bg-green-50 border-green-200';
            case 'B': return 'text-blue-600 bg-blue-50 border-blue-200';
            case 'C': return 'text-yellow-600 bg-yellow-50 border-yellow-200';
            case 'D': return 'text-orange-600 bg-orange-50 border-orange-200';
            case 'F': return 'text-red-600 bg-red-50 border-red-200';
            default: return 'text-gray-600 bg-gray-50 border-gray-200';
        }
    };

    // Get importance badge color
    const getImportanceColor = (importance) => {
        switch (importance) {
            case 'critical': return 'bg-red-100 text-red-800';
            case 'high': return 'bg-orange-100 text-orange-800';
            case 'medium': return 'bg-yellow-100 text-yellow-800';
            case 'low': return 'bg-gray-100 text-gray-800';
            default: return 'bg-gray-100 text-gray-800';
        }
    };

    if (!clientId) {
        return (
            <EmptyState
                icon="user-x"
                title="No Client Selected"
                description="Please select a client from the dropdown above to analyze their intelligence."
            />
        );
    }

    return (
        <div className="space-y-6">
            {/* Action Buttons */}
            <div className="flex items-center gap-4">
                <Button
                    onClick={runFullGrading}
                    disabled={loading || quickLoading}
                    loading={loading}
                    className="gap-2"
                >
                    <Icon name="sparkles" className="h-4 w-4" />
                    Run Full Analysis
                </Button>
                <Button
                    onClick={runQuickAssessment}
                    disabled={loading || quickLoading}
                    loading={quickLoading}
                    variant="outline"
                    className="gap-2"
                >
                    <Icon name="zap" className="h-4 w-4" />
                    Quick Assessment
                </Button>
                <span className="text-sm text-muted-foreground">
                    Full analysis uses AI, quick uses keyword matching
                </span>
            </div>

            {/* Error State */}
            {error && (
                <Alert variant="destructive">
                    <Icon name="alert-circle" className="h-4 w-4" />
                    <AlertTitle>Analysis Failed</AlertTitle>
                    <AlertDescription>{error}</AlertDescription>
                </Alert>
            )}

            {/* Results */}
            {grade && (
                <div className="space-y-6">
                    {/* Grade Overview */}
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                        {/* Overall Grade */}
                        <div className={`p-6 rounded-xl border-2 ${getGradeColor(grade.overall_grade)} text-center`}>
                            <div className="text-6xl font-black">{grade.overall_grade}</div>
                            <div className="text-lg font-medium mt-1">{grade.overall_score}%</div>
                            <div className="text-sm opacity-75 mt-1">
                                {grade.is_quick_assessment ? 'Estimated Grade' : 'Overall Grade'}
                            </div>
                        </div>

                        {/* Stats */}
                        <div className="p-6 rounded-xl border border-gray-200 bg-white">
                            <div className="text-sm text-gray-500 mb-1">Documents Analyzed</div>
                            <div className="text-3xl font-bold">{grade.documents_analyzed || 0}</div>
                        </div>
                        <div className="p-6 rounded-xl border border-gray-200 bg-white">
                            <div className="text-sm text-gray-500 mb-1">Fields Found</div>
                            <div className="text-3xl font-bold">
                                {grade.fields_found || 0}
                                <span className="text-lg font-normal text-gray-400">/{grade.total_fields || 0}</span>
                            </div>
                        </div>
                        <div className="p-6 rounded-xl border border-gray-200 bg-white">
                            <div className="text-sm text-gray-500 mb-1">Ready for Generation</div>
                            <div className={`text-3xl font-bold ${grade.ready_for_generation ? 'text-green-600' : 'text-red-600'}`}>
                                {grade.ready_for_generation ? 'Yes' : 'No'}
                            </div>
                        </div>
                    </div>

                    {/* Quick Assessment Note */}
                    {grade.is_quick_assessment && (
                        <Alert>
                            <Icon name="info" className="h-4 w-4" />
                            <AlertTitle>Quick Assessment</AlertTitle>
                            <AlertDescription>
                                {grade.note || 'This is a keyword-based estimate. Run Full Analysis for AI-powered detailed grading.'}
                            </AlertDescription>
                        </Alert>
                    )}

                    {/* Generation Warnings */}
                    {grade.generation_warnings?.length > 0 && (
                        <Alert variant="warning">
                            <Icon name="alert-triangle" className="h-4 w-4" />
                            <AlertTitle>Generation Warnings</AlertTitle>
                            <AlertDescription>
                                <ul className="list-disc list-inside mt-2 space-y-1">
                                    {grade.generation_warnings.map((warning, i) => (
                                        <li key={i}>{warning}</li>
                                    ))}
                                </ul>
                            </AlertDescription>
                        </Alert>
                    )}

                    {/* Dimension Scores */}
                    {grade.dimension_scores && Object.keys(grade.dimension_scores).length > 0 && (
                        <div className="space-y-4">
                            <h3 className="text-lg font-semibold">Dimension Scores</h3>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {Object.entries(grade.dimension_scores).map(([key, dim]) => (
                                    <div key={key} className="p-4 rounded-lg border border-gray-200 bg-white">
                                        <div className="flex items-center justify-between mb-2">
                                            <span className="font-medium">{dim.display_name}</span>
                                            <span className={`px-2 py-0.5 rounded text-sm font-bold ${getGradeColor(dim.grade)}`}>
                                                {dim.grade} ({dim.score}%)
                                            </span>
                                        </div>
                                        <Progress value={dim.score} className="h-2" />
                                        <div className="mt-2 text-xs text-gray-500">
                                            Weight: {(dim.weight * 100).toFixed(0)}% |
                                            Points: {dim.earned_points}/{dim.max_points}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Critical Gaps */}
                    {grade.critical_gaps?.length > 0 && (
                        <div className="space-y-4">
                            <h3 className="text-lg font-semibold text-red-600">
                                Critical Gaps ({grade.critical_gaps.length})
                            </h3>
                            <div className="space-y-3">
                                {grade.critical_gaps.map((gap, i) => (
                                    <div key={i} className="p-4 rounded-lg border border-red-200 bg-red-50">
                                        <div className="flex items-start justify-between gap-4">
                                            <div className="flex-1">
                                                <div className="flex items-center gap-2 mb-1">
                                                    <span className="font-medium">{gap.display_name}</span>
                                                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${getImportanceColor(gap.importance)}`}>
                                                        {gap.importance}
                                                    </span>
                                                </div>
                                                <p className="text-sm text-gray-600">{gap.impact}</p>
                                                <p className="text-sm text-blue-600 mt-1">{gap.suggestion}</p>
                                            </div>
                                            <div className="text-right text-sm">
                                                <div className="text-gray-500">{gap.dimension}</div>
                                                <div className="text-green-600 font-medium">+{gap.expected_improvement}%</div>
                                            </div>
                                        </div>
                                        {gap.quick_capture_prompt && (
                                            <div className="mt-3 p-3 rounded bg-white border border-gray-200">
                                                <div className="text-xs text-gray-500 mb-1">Quick Capture Question:</div>
                                                <div className="text-sm italic">{gap.quick_capture_prompt}</div>
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Recommendations */}
                    {grade.recommendations?.length > 0 && (
                        <div className="space-y-4">
                            <h3 className="text-lg font-semibold">Top Recommendations</h3>
                            <div className="space-y-3">
                                {grade.recommendations.map((rec, i) => (
                                    <div key={i} className="p-4 rounded-lg border border-gray-200 bg-white flex items-start gap-4">
                                        <div className="flex-shrink-0 h-8 w-8 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center font-bold">
                                            {rec.priority}
                                        </div>
                                        <div className="flex-1">
                                            <div className="font-medium">{rec.action}</div>
                                            <div className="text-sm text-gray-500 mt-1">
                                                {rec.dimension} • Expected improvement: +{rec.expected_improvement}%
                                            </div>
                                        </div>
                                        {rec.template_available && (
                                            <Badge variant="secondary">Template Available</Badge>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Dimension Summaries (for quick assessment) */}
                    {grade.dimension_summaries && (
                        <div className="space-y-4">
                            <h3 className="text-lg font-semibold">Dimension Coverage</h3>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {Object.entries(grade.dimension_summaries).map(([key, dim]) => (
                                    <div key={key} className="p-4 rounded-lg border border-gray-200 bg-white">
                                        <div className="flex items-center justify-between mb-2">
                                            <span className="font-medium">{dim.display_name}</span>
                                            <span className="text-sm text-gray-500">
                                                {dim.fields_found}/{dim.total_fields} fields
                                            </span>
                                        </div>
                                        <Progress value={dim.coverage} className="h-2" />
                                        <div className="mt-1 text-xs text-gray-500 text-right">
                                            {dim.coverage}% coverage
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Initial State */}
            {!grade && !loading && !quickLoading && !error && (
                <div className="text-center py-12 border-2 border-dashed border-gray-200 rounded-xl">
                    <Icon name="bar-chart-3" className="h-12 w-12 mx-auto text-gray-400 mb-4" />
                    <h3 className="text-lg font-medium text-gray-900 mb-2">
                        Intelligence Gap Analysis
                    </h3>
                    <p className="text-gray-500 max-w-md mx-auto mb-6">
                        Analyze your client's knowledge base to identify gaps and get a grade
                        indicating readiness for high-quality email calendar generation.
                    </p>
                    <div className="text-sm text-gray-400">
                        Click "Run Full Analysis" or "Quick Assessment" above to begin
                    </div>
                </div>
            )}
        </div>
    );
}

// ============================================================================
// TEXT CONTENT UPLOAD COMPONENT
// ============================================================================
function TextContentUpload({ onUpload, uploading }) {
    const [content, setContent] = useState('');

    const handleSubmit = () => {
        if (content.trim()) {
            onUpload(content);
            setContent('');
        }
    };

    return (
        <div className="space-y-3">
            <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Paste your text content here..."
                className="w-full min-h-[120px] rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-y"
                disabled={uploading}
            />
            <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">
                    {content.length.toLocaleString()} characters
                </span>
                <Button
                    onClick={handleSubmit}
                    disabled={!content.trim() || uploading}
                    loading={uploading}
                >
                    Upload Text
                </Button>
            </div>
        </div>
    );
}

// ============================================================================
// RENDER APP
// ============================================================================
const container = document.getElementById('root');
const root = ReactDOM.createRoot(container);
root.render(<App />);
