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
import { RAGManager } from './components/RAGManager.jsx';
import { useRAGSearch, useDocuments, useUpload, useToast } from './hooks/useRAG.js';

const { useState, useEffect, useCallback } = React;

function waitForAuthReady() {
    if (typeof EmailPilotAuth !== 'undefined') {
        return EmailPilotAuth.ready();
    }
    return new Promise((resolve) => {
        const check = () => {
            if (typeof EmailPilotAuth !== 'undefined') {
                EmailPilotAuth.ready().then(resolve);
            } else {
                setTimeout(check, 100);
            }
        };
        check();
    });
}

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
    const [activeTab, setActiveTab] = useState('intelligence');
    const [libraryMode, setLibraryMode] = useState('browse');
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

    // Initialize - wait for auth controller before fetching clients
    useEffect(() => {
        let cancelled = false;
        const init = async () => {
            await waitForAuthReady();
            if (!cancelled) {
                fetchClients();
            }
        };
        init();
        return () => {
            cancelled = true;
        };
    }, [fetchClients]);

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
                                <TabsTrigger value="intelligence">
                                    <Icon name="sparkles" className="h-4 w-4 mr-2" />
                                    Intelligence
                                </TabsTrigger>
                                <TabsTrigger value="library">
                                    <Icon name="library" className="h-4 w-4 mr-2" />
                                    Library
                                </TabsTrigger>
                                <TabsTrigger value="manage">
                                    <Icon name="activity" className="h-4 w-4 mr-2" />
                                    Manage
                                </TabsTrigger>
                                <TabsTrigger value="user">
                                    <Icon name="settings" className="h-4 w-4 mr-2" />
                                    Settings
                                </TabsTrigger>
                            </TabsList>
                                
                            {/* Intelligence Tab — Upload (left) + Grade (right) */}
                            <TabsContent value="intelligence">
                                {!selectedClient ? (
                                    <EmptyState
                                        icon="user-x"
                                        title="No Client Selected"
                                        description="Please select a client from the dropdown above to start uploading documents and view your intelligence grade."
                                    />
                                ) : (
                                    <div className="flex flex-col lg:flex-row gap-6">
                                        {/* LEFT: Upload Panel */}
                                        <div className="flex-1 min-w-0 space-y-6">
                                            <h3 className="text-lg font-semibold flex items-center gap-2">
                                                <Icon name="upload-cloud" className="h-5 w-5 text-blue-600" />
                                                Upload Knowledge
                                            </h3>

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

                                        {/* RIGHT: Grade Checklist Panel */}
                                        <div className="lg:w-[420px] flex-shrink-0">
                                            <IntelligenceGrading
                                                clientId={selectedClient}
                                                toast={toast}
                                                compact={true}
                                            />
                                        </div>
                                    </div>
                                )}
                            </TabsContent>

                            {/* Library Tab — Browse + Semantic Search toggle */}
                            <TabsContent value="library">
                                {!selectedClient ? (
                                    <EmptyState
                                        icon="user-x"
                                        title="No Client Selected"
                                        description="Please select a client from the dropdown above to browse documents."
                                    />
                                ) : (
                                    <div className="space-y-4">
                                        {/* Browse / Search Toggle */}
                                        <div className="flex items-center gap-1 p-1 bg-gray-100 rounded-lg w-fit">
                                            <button
                                                onClick={() => setLibraryMode('browse')}
                                                className={`px-4 py-2 rounded-md text-sm font-medium transition-all flex items-center gap-2 ${libraryMode === 'browse' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900'}`}
                                            >
                                                <Icon name="library" className="h-4 w-4" />
                                                Browse
                                            </button>
                                            <button
                                                onClick={() => setLibraryMode('search')}
                                                className={`px-4 py-2 rounded-md text-sm font-medium transition-all flex items-center gap-2 ${libraryMode === 'search' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-600 hover:text-gray-900'}`}
                                            >
                                                <Icon name="sparkles" className="h-4 w-4" />
                                                Semantic Search
                                            </button>
                                        </div>

                                        {/* Content based on mode */}
                                        {libraryMode === 'browse' ? (
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
                                                onSwitchToUpload={() => setActiveTab('intelligence')}
                                            />
                                        ) : (
                                            <RAGSearch
                                                clientId={selectedClient}
                                                results={search.results}
                                                loading={search.loading}
                                                error={search.error}
                                                onSearch={handleSearch}
                                            />
                                        )}
                                    </div>
                                )}
                            </TabsContent>

                            {/* Manage Tab — Audit & Prune */}
                            <TabsContent value="manage">
                                <RAGManager clientId={selectedClient} toast={toast} />
                            </TabsContent>

                            {/* Settings Tab */}
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
// INTELLIGENCE GRADING COMPONENT (Enhanced with A+ Guidance & Upload Accordions)
// ============================================================================
function IntelligenceGrading({ clientId, toast, compact = false }) {
    const [loading, setLoading] = useState(false);
    const [quickLoading, setQuickLoading] = useState(false);
    const [grade, setGrade] = useState(null);
    const [error, setError] = useState(null);
    const [requirements, setRequirements] = useState(null);
    const [expandedAccordions, setExpandedAccordions] = useState({});
    const [uploadingField, setUploadingField] = useState(null);
    const [quickCaptureText, setQuickCaptureText] = useState({});
    const [completedFields, setCompletedFields] = useState(new Set()); // Track completed uploads
    const [reanalyzeNeeded, setReanalyzeNeeded] = useState(false); // Show re-analyze prompt
    const [lastGradedAt, setLastGradedAt] = useState(null);

    // Fetch requirements config on mount
    useEffect(() => {
        const fetchRequirements = async () => {
            try {
                const response = await fetch(
                    `${window.RAG_CONFIG?.serviceUrl || ''}/api/intelligence/requirements`
                );
                if (response.ok) {
                    const data = await response.json();
                    setRequirements(data);
                }
            } catch (err) {
                console.error('Failed to fetch requirements:', err);
            }
        };
        fetchRequirements();
    }, []);

    // Auto-load last grade when client changes
    useEffect(() => {
        if (!clientId) {
            setGrade(null);
            setLastGradedAt(null);
            return;
        }
        let cancelled = false;
        const fetchLastGrade = async () => {
            try {
                const response = await fetch(
                    `${window.RAG_CONFIG?.serviceUrl || ''}/api/intelligence/last-grade/${clientId}`
                );
                if (response.ok && !cancelled) {
                    const data = await response.json();
                    setGrade(data);
                    setLastGradedAt(data.saved_at || data.graded_at || null);
                }
            } catch (err) {
                // 404 is expected for clients with no grade yet
                console.debug('No cached grade:', err);
            }
        };
        fetchLastGrade();
        return () => { cancelled = true; };
    }, [clientId]);

    // Toggle accordion
    const toggleAccordion = (key) => {
        setExpandedAccordions(prev => ({ ...prev, [key]: !prev[key] }));
    };

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
            setLastGradedAt(new Date().toISOString());
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

    // Handle quick capture - text or file submission
    const handleQuickCapture = async (fieldName, content, file = null) => {
        if (!content?.trim() && !file) return;

        setUploadingField(fieldName);
        try {
            let response;

            if (file) {
                // File upload - use the main upload endpoint with auto-categorization
                const formData = new FormData();
                formData.append('file', file);
                formData.append('client_id', clientId);
                formData.append('title', `${fieldName} - ${file.name}`);
                formData.append('source_type', 'quick_capture');
                formData.append('auto_categorize', 'true'); // Enable AI categorization
                formData.append('field_name', fieldName);

                response = await fetch(
                    `${window.RAG_CONFIG?.serviceUrl || ''}/api/documents/${clientId}/upload`,
                    {
                        method: 'POST',
                        body: formData,
                        credentials: 'include'
                    }
                );
            } else {
                // Text submission - use enhanced quick-capture endpoint
                response = await fetch(
                    `${window.RAG_CONFIG?.serviceUrl || ''}/api/intelligence/quick-capture`,
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            client_id: clientId,
                            answers: [{ field_name: fieldName, content: content.trim() }],
                            auto_categorize: true // Enable AI categorization for text too
                        })
                    }
                );
            }

            if (response.ok) {
                const result = await response.json();
                const categoryInfo = result.categorization ? ` (categorized as ${result.categorization.category})` : '';
                toast.success(`✓ Saved${categoryInfo}! Click "Re-analyze" to see your updated score.`);

                // Mark field as completed, collapse accordion
                setCompletedFields(prev => new Set([...prev, fieldName]));
                setQuickCaptureText(prev => ({ ...prev, [fieldName]: '' }));
                setExpandedAccordions(prev => ({ ...prev, [fieldName]: false, [`gap-${fieldName}`]: false, [`quick-${fieldName}`]: false }));
                setReanalyzeNeeded(true);
            } else {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to save');
            }
        } catch (err) {
            toast.error(err.message || 'Failed to save information');
        } finally {
            setUploadingField(null);
        }
    };

    // Re-analyze after uploads
    const handleReanalyze = () => {
        setReanalyzeNeeded(false);
        setCompletedFields(new Set());
        if (grade?.is_quick_assessment) {
            runQuickAssessment();
        } else {
            runFullGrading();
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

    // Calculate points needed for A+
    const getPointsToA = (currentScore) => {
        return Math.max(0, 100 - currentScore);
    };

    // Get field requirements for a dimension
    const getFieldRequirements = (dimKey) => {
        if (!requirements?.dimensions?.[dimKey]) return [];
        return requirements.dimensions[dimKey].fields || [];
    };

    if (!clientId) {
        return (
            <EmptyState
                icon="user-x"
                title="No Client Selected"
                description={compact ? "Select a client above." : "Please select a client from the dropdown above to analyze their intelligence."}
            />
        );
    }

    return (
        <div className="space-y-4">
            {/* Header with Grade Summary (compact) or Action Buttons (full) */}
            {compact ? (
                <div className="space-y-3">
                    <h3 className="text-lg font-semibold flex items-center gap-2">
                        <Icon name="bar-chart-3" className="h-5 w-5 text-indigo-600" />
                        Intelligence Grade
                    </h3>
                    {lastGradedAt && (
                        <p className="text-xs text-muted-foreground">
                            Last graded: {new Date(lastGradedAt).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                        </p>
                    )}
                    <div className="flex gap-2">
                        <Button
                            onClick={runFullGrading}
                            disabled={loading || quickLoading}
                            loading={loading}
                            size="sm"
                            className="gap-1.5 text-xs"
                        >
                            <Icon name="sparkles" className="h-3.5 w-3.5" />
                            Full Analysis
                        </Button>
                        <Button
                            onClick={runQuickAssessment}
                            disabled={loading || quickLoading}
                            loading={quickLoading}
                            variant="outline"
                            size="sm"
                            className="gap-1.5 text-xs"
                        >
                            <Icon name="zap" className="h-3.5 w-3.5" />
                            Quick
                        </Button>
                    </div>
                </div>
            ) : (
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
            )}

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
                <div className="space-y-4">
                    {/* Grade Overview — compact or full */}
                    {compact ? (
                        <div className="space-y-3">
                            {/* Compact grade header */}
                            <div className={`p-4 rounded-xl border-2 ${getGradeColor(grade.overall_grade)} flex items-center gap-4`}>
                                <div className="text-4xl font-black">{grade.overall_grade}</div>
                                <div className="flex-1">
                                    <div className="text-lg font-bold">{grade.overall_score}%</div>
                                    <div className="text-xs opacity-75">
                                        {grade.is_quick_assessment ? 'Estimated' : 'Full Analysis'}
                                    </div>
                                </div>
                                <div className={`text-sm font-semibold ${grade.ready_for_generation ? 'text-green-600' : 'text-red-600'}`}>
                                    {grade.ready_for_generation ? 'Ready' : 'Not Ready'}
                                </div>
                            </div>
                            <div className="flex gap-3 text-xs text-gray-500">
                                <span>{grade.documents_analyzed || 0} docs</span>
                                <span>{grade.fields_found || 0}/{grade.total_fields || 0} fields</span>
                            </div>
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                            <div className={`p-6 rounded-xl border-2 ${getGradeColor(grade.overall_grade)} text-center`}>
                                <div className="text-6xl font-black">{grade.overall_grade}</div>
                                <div className="text-lg font-medium mt-1">{grade.overall_score}%</div>
                                <div className="text-sm opacity-75 mt-1">
                                    {grade.is_quick_assessment ? 'Estimated Grade' : 'Overall Grade'}
                                </div>
                            </div>
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
                    )}

                    {/* Re-analyze Banner - Shows after uploads */}
                    {reanalyzeNeeded && (
                        <div className="p-4 rounded-2xl bg-gradient-to-r from-blue-500 to-indigo-600 text-white shadow-lg">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <div className="p-2 bg-white/20 rounded-xl">
                                        <Icon name="refresh-cw" className="h-5 w-5" />
                                    </div>
                                    <div>
                                        <h4 className="font-semibold">New information added!</h4>
                                        <p className="text-sm text-blue-100">Re-analyze to see your updated Intelligence Grade.</p>
                                    </div>
                                </div>
                                <button
                                    onClick={handleReanalyze}
                                    className="px-5 py-2.5 bg-white text-blue-600 rounded-xl font-semibold hover:bg-blue-50 transition-all shadow-md hover:shadow-lg"
                                >
                                    Re-analyze Now
                                </button>
                            </div>
                        </div>
                    )}

                    {/* Compact checklist mode — shows all fields as check/x rows */}
                    {compact && grade.dimension_scores && (
                        <div className="space-y-3">
                            <h4 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">Checklist</h4>
                            {Object.entries(grade.dimension_scores).map(([key, dim]) => (
                                <div key={key} className="space-y-1">
                                    <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider mt-2">
                                        {dim.display_name} ({dim.grade})
                                    </div>
                                    {dim.fields?.map((field, i) => (
                                        <div key={i} className="flex items-center gap-2 py-1">
                                            {field.found ? (
                                                <Icon name="check-circle" className="h-4 w-4 text-green-500 flex-shrink-0" />
                                            ) : completedFields.has(field.field_name) ? (
                                                <Icon name="clock" className="h-4 w-4 text-blue-500 flex-shrink-0" />
                                            ) : (
                                                <Icon name="x-circle" className="h-4 w-4 text-red-400 flex-shrink-0" />
                                            )}
                                            <span className={`text-sm ${field.found ? 'text-gray-700' : 'text-gray-500'}`}>
                                                {field.display_name}
                                            </span>
                                            {field.found && field.coverage < 80 && (
                                                <span className="text-[10px] text-yellow-600">({Math.round(field.coverage)}%)</span>
                                            )}
                                        </div>
                                    ))}
                                    {/* Show gap prompts for missing fields */}
                                    {dim.gaps?.filter(g => !g.found && !completedFields.has(g.field_name)).map((gap, i) => (
                                        gap.quick_capture_prompt && (
                                            <div key={`hint-${i}`} className="ml-6 text-xs text-gray-400 italic">
                                                {gap.quick_capture_prompt}
                                            </div>
                                        )
                                    ))}
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Full mode content below */}
                    {!compact && (
                        <>
                            {/* Path to A+ Guidance */}
                            {grade.overall_grade !== 'A' && !reanalyzeNeeded && (
                                <div className="p-5 rounded-2xl border border-emerald-200 bg-gradient-to-br from-emerald-50 via-green-50 to-teal-50">
                                    <h3 className="text-lg font-bold text-emerald-800 mb-3 flex items-center gap-2">
                                        <Icon name="trending-up" className="h-5 w-5" />
                                        Path to A+ ({getPointsToA(grade.overall_score)} points needed)
                                    </h3>
                                    <p className="text-sm text-emerald-700 mb-4">
                                        Focus on these high-impact improvements:
                                    </p>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                        {(grade.critical_gaps || []).slice(0, 4).map((item, i) => (
                                            <div key={i} className="flex items-center gap-3 p-3 bg-white/60 rounded-xl border border-emerald-100">
                                                <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-emerald-100 flex items-center justify-center text-emerald-600 font-bold text-sm">
                                                    {i + 1}
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <span className="text-sm text-emerald-800 line-clamp-1">{item.action || item.display_name}</span>
                                                </div>
                                                <span className="text-emerald-600 font-semibold text-sm whitespace-nowrap">+{item.expected_improvement}%</span>
                                            </div>
                                        ))}
                                    </div>
                                    <p className="text-xs text-emerald-600 mt-4 flex items-center gap-1">
                                        <Icon name="info" className="h-3 w-3" />
                                        Expand the cards below to add missing information
                                    </p>
                                </div>
                            )}

                            {/* Quick Assessment Note */}
                            {grade.is_quick_assessment && (
                                <Alert>
                                    <Icon name="info" className="h-4 w-4" />
                                    <AlertTitle>Quick Assessment - Keyword Matching</AlertTitle>
                                    <AlertDescription>
                                        <p className="mb-2">{grade.note || 'This is a keyword-based estimate. Run Full Analysis for AI-powered detailed grading.'}</p>
                                        <p className="text-xs text-muted-foreground">
                                            <strong>How it works:</strong> The quick assessment scans your documents for specific keywords related to each field.
                                            If no keywords are found, that field is marked as missing. See the "What We Searched For" sections below for details.
                                        </p>
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

                            {/* Dimension Scores with Accordions */}
                            {grade.dimension_scores && Object.keys(grade.dimension_scores).length > 0 && (
                                <div className="space-y-4">
                                    <h3 className="text-lg font-semibold">Dimension Scores</h3>
                                    <div className="space-y-4">
                                        {Object.entries(grade.dimension_scores).map(([key, dim]) => (
                                            <DimensionScoreCard
                                                key={key}
                                                dimKey={key}
                                                dim={dim}
                                                requirements={requirements}
                                                isExpanded={expandedAccordions[key]}
                                                onToggle={() => toggleAccordion(key)}
                                                getGradeColor={getGradeColor}
                                                getImportanceColor={getImportanceColor}
                                                clientId={clientId}
                                                toast={toast}
                                                quickCaptureText={quickCaptureText}
                                                setQuickCaptureText={setQuickCaptureText}
                                                uploadingField={uploadingField}
                                                onQuickCapture={handleQuickCapture}
                                                isQuickAssessment={grade.is_quick_assessment}
                                                completedFields={completedFields}
                                            />
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Critical Gaps with Upload Accordions */}
                            {grade.critical_gaps?.length > 0 && (
                                <div className="space-y-4">
                                    <h3 className="text-lg font-semibold text-red-600 flex items-center gap-2">
                                        <Icon name="alert-triangle" className="h-5 w-5" />
                                        Critical Gaps ({grade.critical_gaps.filter(g => !completedFields.has(g.field_name)).length} remaining)
                                    </h3>
                                    <div className="space-y-3">
                                        {grade.critical_gaps.map((gap, i) => (
                                            <GapCard
                                                key={i}
                                                gap={gap}
                                                index={i}
                                                isExpanded={expandedAccordions[`gap-${gap.field_name}`]}
                                                onToggle={() => toggleAccordion(`gap-${gap.field_name}`)}
                                                getImportanceColor={getImportanceColor}
                                                clientId={clientId}
                                                toast={toast}
                                                quickCaptureText={quickCaptureText}
                                                setQuickCaptureText={setQuickCaptureText}
                                                uploadingField={uploadingField}
                                                onQuickCapture={handleQuickCapture}
                                                requirements={requirements}
                                                isQuickAssessment={grade.is_quick_assessment}
                                                isCompleted={completedFields.has(gap.field_name)}
                                            />
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Dimension Summaries (for quick assessment) with Details */}
                            {grade.dimension_summaries && (
                                <div className="space-y-4">
                                    <h3 className="text-lg font-semibold">Dimension Coverage</h3>
                                    <div className="space-y-4">
                                        {Object.entries(grade.dimension_summaries).map(([key, dim]) => (
                                            <QuickAssessmentDimensionCard
                                                key={key}
                                                dimKey={key}
                                                dim={dim}
                                                requirements={requirements}
                                                isExpanded={expandedAccordions[`quick-${key}`]}
                                                onToggle={() => toggleAccordion(`quick-${key}`)}
                                                clientId={clientId}
                                                toast={toast}
                                                quickCaptureText={quickCaptureText}
                                                setQuickCaptureText={setQuickCaptureText}
                                                uploadingField={uploadingField}
                                                onQuickCapture={handleQuickCapture}
                                                completedFields={completedFields}
                                            />
                                        ))}
                                    </div>
                                </div>
                            )}
                        </>
                    )}
                </div>
            )}

            {/* Initial State */}
            {!grade && !loading && !quickLoading && !error && (
                <div className={`text-center border-2 border-dashed border-gray-200 rounded-xl ${compact ? 'py-8' : 'py-12'}`}>
                    <Icon name="bar-chart-3" className={`mx-auto text-gray-400 mb-4 ${compact ? 'h-8 w-8' : 'h-12 w-12'}`} />
                    <h3 className={`font-medium text-gray-900 mb-2 ${compact ? 'text-base' : 'text-lg'}`}>
                        Intelligence Gap Analysis
                    </h3>
                    <p className={`text-gray-500 mx-auto mb-4 ${compact ? 'text-sm max-w-xs' : 'max-w-md mb-6'}`}>
                        {compact
                            ? 'Analyze your knowledge base to see what\'s missing.'
                            : 'Analyze your client\'s knowledge base to identify gaps and get a grade indicating readiness for high-quality email calendar generation.'
                        }
                    </p>
                    <div className="text-sm text-gray-400">
                        Click {compact ? '"Full Analysis" or "Quick"' : '"Run Full Analysis" or "Quick Assessment"'} above to begin
                    </div>
                </div>
            )}
        </div>
    );
}

// ============================================================================
// DIMENSION SCORE CARD (Full Analysis) - With Accordion Upload
// ============================================================================
function DimensionScoreCard({
    dimKey, dim, requirements, isExpanded, onToggle, getGradeColor, getImportanceColor,
    clientId, toast, quickCaptureText, setQuickCaptureText, uploadingField, onQuickCapture, isQuickAssessment, completedFields = new Set()
}) {
    const isNotPerfect = dim.score < 100;
    const fieldRequirements = requirements?.dimensions?.[dimKey]?.fields || [];
    const missingCount = dim.fields?.filter(f => !f.found && !completedFields.has(f.field_name)).length || 0;
    const lowCoverageCount = dim.fields?.filter(f => f.found && f.coverage < 80).length || 0;
    const hasImprovements = missingCount > 0 || lowCoverageCount > 0 || (dim.gaps?.length > 0);

    return (
        <div className={`rounded-2xl border ${isNotPerfect ? 'border-gray-200' : 'border-green-300'} bg-white overflow-hidden shadow-sm hover:shadow-md transition-shadow`}>
            {/* Main Score Header */}
            <div className="p-5">
                <div className="flex items-center justify-between mb-3">
                    <span className="font-semibold text-gray-900">{dim.display_name}</span>
                    <span className={`px-3 py-1 rounded-full text-sm font-bold ${getGradeColor(dim.grade)}`}>
                        {dim.grade} • {dim.score}%
                    </span>
                </div>
                <div className="relative h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div
                        className={`absolute inset-y-0 left-0 rounded-full transition-all duration-500 ${dim.score >= 90 ? 'bg-green-500' : dim.score >= 70 ? 'bg-blue-500' : dim.score >= 50 ? 'bg-yellow-500' : 'bg-red-500'}`}
                        style={{ width: `${dim.score}%` }}
                    />
                </div>
                <div className="mt-2 flex justify-between text-xs text-gray-500">
                    <span>Weight: {(dim.weight * 100).toFixed(0)}%</span>
                    <span>{dim.earned_points}/{dim.max_points} points</span>
                </div>

                {/* Fields Found vs Missing Summary */}
                {dim.fields && (
                    <div className="mt-4 flex flex-wrap gap-2">
                        {dim.fields.filter(f => f.found && f.coverage >= 80).map((field, i) => (
                            <span key={i} className="text-xs px-2.5 py-1 bg-green-50 text-green-700 rounded-lg font-medium flex items-center gap-1">
                                <Icon name="check" className="h-3 w-3" />
                                {field.display_name}
                            </span>
                        ))}
                        {dim.fields.filter(f => f.found && f.coverage < 80).map((field, i) => (
                            <span key={i} className="text-xs px-2.5 py-1 bg-yellow-50 text-yellow-700 rounded-lg font-medium flex items-center gap-1">
                                <Icon name="check" className="h-3 w-3" />
                                {field.display_name}
                                <span className="text-yellow-500 text-[10px]">({Math.round(field.coverage)}%)</span>
                            </span>
                        ))}
                        {dim.fields.filter(f => !f.found).map((field, i) => (
                            <span key={i} className={`text-xs px-2.5 py-1 rounded-lg font-medium flex items-center gap-1 ${completedFields.has(field.field_name) ? 'bg-blue-50 text-blue-700' : 'bg-red-50 text-red-700'}`}>
                                <Icon name={completedFields.has(field.field_name) ? "clock" : "x"} className="h-3 w-3" />
                                {field.display_name}
                                {completedFields.has(field.field_name) && <span className="text-[10px]">(pending)</span>}
                            </span>
                        ))}
                    </div>
                )}
            </div>

            {/* Expand Button for Non-Perfect Scores */}
            {isNotPerfect && hasImprovements && (
                <button
                    onClick={onToggle}
                    className="w-full px-5 py-3 bg-gradient-to-r from-blue-50 to-indigo-50 border-t border-gray-100 text-sm font-medium text-blue-700 hover:from-blue-100 hover:to-indigo-100 transition-all flex items-center justify-center gap-2"
                >
                    <Icon name={isExpanded ? "chevron-up" : "plus-circle"} className="h-4 w-4" />
                    {isExpanded ? 'Collapse' : missingCount > 0
                        ? `Add ${missingCount} Missing Field${missingCount > 1 ? 's' : ''} (+${Math.round(100 - dim.score)}%)`
                        : `Improve ${lowCoverageCount} Field${lowCoverageCount > 1 ? 's' : ''} (+${Math.round(100 - dim.score)}%)`
                    }
                </button>
            )}

            {/* Expanded Accordion Content */}
            {isExpanded && isNotPerfect && (
                <div className="p-5 border-t border-gray-100 bg-gradient-to-b from-gray-50 to-white animate-fade-in">
                    {/* Per-field coverage breakdown */}
                    {dim.fields && dim.fields.length > 0 && (
                        <div className="mb-4 space-y-2">
                            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Field Coverage</span>
                            {dim.fields.map((field, i) => (
                                <div key={i} className="flex items-center gap-3">
                                    <span className="text-xs text-gray-700 w-40 truncate" title={field.display_name}>{field.display_name}</span>
                                    <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                                        <div
                                            className={`h-full rounded-full ${field.coverage >= 80 ? 'bg-green-400' : field.coverage >= 50 ? 'bg-yellow-400' : 'bg-red-400'}`}
                                            style={{ width: `${Math.min(field.coverage, 100)}%` }}
                                        />
                                    </div>
                                    <span className={`text-xs font-medium w-10 text-right ${field.coverage >= 80 ? 'text-green-600' : field.coverage >= 50 ? 'text-yellow-600' : 'text-red-600'}`}>
                                        {Math.round(field.coverage)}%
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Gaps — missing fields + low-coverage improvement suggestions */}
                    {dim.gaps?.length > 0 && (
                        <div className="space-y-4">
                            {dim.gaps.filter(g => !completedFields.has(g.field_name)).map((gap, i) => (
                                <QuickCaptureUpload
                                    key={i}
                                    fieldName={gap.field_name}
                                    displayName={gap.display_name}
                                    prompt={gap.quick_capture_prompt}
                                    expectedImprovement={gap.expected_improvement}
                                    importance={gap.importance}
                                    value={quickCaptureText[gap.field_name] || ''}
                                    onChange={(val) => setQuickCaptureText(prev => ({ ...prev, [gap.field_name]: val }))}
                                    onSubmit={(file) => onQuickCapture(gap.field_name, quickCaptureText[gap.field_name], file)}
                                    isLoading={uploadingField === gap.field_name}
                                    getImportanceColor={getImportanceColor}
                                />
                            ))}
                        </div>
                    )}

                    {/* Collapsible: What We Searched For */}
                    {isQuickAssessment && fieldRequirements.length > 0 && (
                        <details className="mt-4 text-sm">
                            <summary className="cursor-pointer text-gray-500 hover:text-gray-700 flex items-center gap-2">
                                <Icon name="info" className="h-4 w-4" />
                                Keywords we searched for
                            </summary>
                            <div className="mt-2 p-3 bg-gray-50 rounded-xl text-xs space-y-2">
                                {fieldRequirements.filter(f => !dim.fields?.find(df => df.field_name === f.name)?.found).map((field, i) => (
                                    <div key={i}>
                                        <span className="font-medium text-gray-700">{field.display_name}:</span>{' '}
                                        <span className="text-gray-500">{field.detection_keywords?.slice(0, 6).join(', ')}</span>
                                    </div>
                                ))}
                            </div>
                        </details>
                    )}
                </div>
            )}
        </div>
    );
}

// ============================================================================
// GAP CARD - With Upload Accordion
// ============================================================================
function GapCard({
    gap, index, isExpanded, onToggle, getImportanceColor, clientId, toast,
    quickCaptureText, setQuickCaptureText, uploadingField, onQuickCapture, requirements, isQuickAssessment, isCompleted = false
}) {
    // Find field requirements for this gap
    const findFieldRequirements = () => {
        if (!requirements?.dimensions) return null;
        for (const [dimKey, dim] of Object.entries(requirements.dimensions)) {
            const field = dim.fields?.find(f => f.name === gap.field_name);
            if (field) return field;
        }
        return null;
    };
    const fieldReq = findFieldRequirements();

    // If completed, show success state
    if (isCompleted) {
        return (
            <div className="rounded-2xl border border-green-200 bg-green-50 p-4 flex items-center gap-4">
                <div className="flex-shrink-0 w-10 h-10 rounded-xl bg-green-100 flex items-center justify-center">
                    <Icon name="check" className="h-5 w-5 text-green-600" />
                </div>
                <div className="flex-1">
                    <span className="font-medium text-green-800">{gap.display_name}</span>
                    <p className="text-sm text-green-600">Added! Re-analyze to update score.</p>
                </div>
                <span className="text-green-600 font-semibold">+{gap.expected_improvement}%</span>
            </div>
        );
    }

    return (
        <div className="rounded-2xl border border-red-200 bg-gradient-to-br from-red-50 to-orange-50 overflow-hidden shadow-sm">
            <div className="p-5">
                <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                            <span className="font-semibold text-gray-900">{gap.display_name}</span>
                            <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${getImportanceColor(gap.importance)}`}>
                                {gap.importance}
                            </span>
                        </div>
                        <p className="text-sm text-gray-600">{gap.impact}</p>
                    </div>
                    <div className="text-right">
                        <div className="text-xs text-gray-500 uppercase tracking-wide">{gap.dimension}</div>
                        <div className="text-lg font-bold text-green-600">+{gap.expected_improvement}%</div>
                    </div>
                </div>
            </div>

            {/* Expand Button */}
            <button
                onClick={onToggle}
                className="w-full px-5 py-3 bg-gradient-to-r from-red-100 to-orange-100 border-t border-red-200 text-sm font-semibold text-red-700 hover:from-red-200 hover:to-orange-200 transition-all flex items-center justify-center gap-2"
            >
                <Icon name={isExpanded ? "chevron-up" : "plus"} className="h-4 w-4" />
                {isExpanded ? 'Collapse' : 'Add This Information'}
            </button>

            {/* Expanded Upload Accordion */}
            {isExpanded && (
                <div className="p-5 border-t border-red-200 bg-white animate-fade-in">
                    <QuickCaptureUpload
                        fieldName={gap.field_name}
                        displayName={gap.display_name}
                        prompt={gap.quick_capture_prompt}
                        expectedImprovement={gap.expected_improvement}
                        importance={gap.importance}
                        value={quickCaptureText[gap.field_name] || ''}
                        onChange={(val) => setQuickCaptureText(prev => ({ ...prev, [gap.field_name]: val }))}
                        onSubmit={(file) => onQuickCapture(gap.field_name, quickCaptureText[gap.field_name], file)}
                        isLoading={uploadingField === gap.field_name}
                        getImportanceColor={getImportanceColor}
                    />
                </div>
            )}
        </div>
    );
}

// ============================================================================
// QUICK ASSESSMENT DIMENSION CARD - With Keywords Shown
// ============================================================================
function QuickAssessmentDimensionCard({
    dimKey, dim, requirements, isExpanded, onToggle, clientId, toast,
    quickCaptureText, setQuickCaptureText, uploadingField, onQuickCapture, completedFields = new Set()
}) {
    const isNotPerfect = dim.coverage < 100;
    const fieldRequirements = requirements?.dimensions?.[dimKey]?.fields || [];
    const missingFields = fieldRequirements.filter(f => {
        // Check if field is missing (not found) and not yet completed
        const dimField = dim.fields_detail?.find(df => df.field_name === f.name);
        return (!dimField || !dimField.found) && !completedFields.has(f.name);
    });

    return (
        <div className={`rounded-2xl border ${isNotPerfect ? 'border-gray-200' : 'border-green-300'} bg-white overflow-hidden shadow-sm hover:shadow-md transition-shadow`}>
            <div className="p-5">
                <div className="flex items-center justify-between mb-3">
                    <span className="font-semibold text-gray-900">{dim.display_name}</span>
                    <span className="text-sm font-medium text-gray-500">
                        {dim.fields_found}/{dim.total_fields} fields
                    </span>
                </div>
                <div className="relative h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div
                        className={`absolute inset-y-0 left-0 rounded-full transition-all duration-500 ${dim.coverage >= 90 ? 'bg-green-500' : dim.coverage >= 70 ? 'bg-blue-500' : dim.coverage >= 50 ? 'bg-yellow-500' : 'bg-red-500'}`}
                        style={{ width: `${dim.coverage}%` }}
                    />
                </div>
                <div className="mt-2 text-xs text-gray-500 text-right">
                    {dim.coverage}% coverage
                </div>
            </div>

            {/* Expand Button */}
            {isNotPerfect && missingFields.length > 0 && (
                <button
                    onClick={onToggle}
                    className="w-full px-5 py-3 bg-gradient-to-r from-blue-50 to-indigo-50 border-t border-gray-100 text-sm font-medium text-blue-700 hover:from-blue-100 hover:to-indigo-100 transition-all flex items-center justify-center gap-2"
                >
                    <Icon name={isExpanded ? "chevron-up" : "plus-circle"} className="h-4 w-4" />
                    {isExpanded ? 'Collapse' : `Add ${missingFields.length} Missing Field${missingFields.length > 1 ? 's' : ''}`}
                </button>
            )}

            {/* Expanded Content */}
            {isExpanded && isNotPerfect && (
                <div className="p-5 border-t border-gray-100 bg-gradient-to-b from-gray-50 to-white animate-fade-in">
                    <div className="space-y-4">
                        {missingFields.map((field, i) => (
                            <div key={i} className="p-4 rounded-xl bg-white border border-gray-200 shadow-sm">
                                <div className="flex items-center justify-between mb-2">
                                    <div className="flex items-center gap-2">
                                        <span className="font-medium text-gray-900">{field.display_name}</span>
                                        <span className={`px-2 py-0.5 text-xs font-semibold rounded-full ${field.importance === 'critical' ? 'bg-red-100 text-red-700' : field.importance === 'high' ? 'bg-orange-100 text-orange-700' : 'bg-gray-100 text-gray-600'}`}>
                                            {field.importance}
                                        </span>
                                    </div>
                                    <span className="text-xs text-gray-400">{field.points} pts</span>
                                </div>
                                <p className="text-sm text-gray-600 mb-3">{field.description}</p>

                                {field.quick_capture_prompt && (
                                    <QuickCaptureUpload
                                        fieldName={field.name}
                                        displayName={field.display_name}
                                        prompt={field.quick_capture_prompt}
                                        expectedImprovement={Math.round(field.points * (requirements?.dimensions?.[dimKey]?.weight || 0.1))}
                                        importance={field.importance}
                                        value={quickCaptureText[field.name] || ''}
                                        onChange={(val) => setQuickCaptureText(prev => ({ ...prev, [field.name]: val }))}
                                        onSubmit={(file) => onQuickCapture(field.name, quickCaptureText[field.name], file)}
                                        isLoading={uploadingField === field.name}
                                        detectionKeywords={field.detection_keywords}
                                    />
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}

// ============================================================================
// QUICK CAPTURE UPLOAD COMPONENT - Text + File Upload Widget
// ============================================================================
function QuickCaptureUpload({
    fieldName, displayName, prompt, expectedImprovement, importance, value, onChange, onSubmit, isLoading, getImportanceColor, detectionKeywords
}) {
    const [uploadMode, setUploadMode] = useState('text'); // 'text' or 'file'
    const [selectedFile, setSelectedFile] = useState(null);
    const fileInputRef = React.useRef(null);

    const handleFileSelect = (e) => {
        const file = e.target.files?.[0];
        if (file) {
            setSelectedFile(file);
        }
    };

    const handleSubmit = () => {
        if (uploadMode === 'file' && selectedFile) {
            onSubmit(selectedFile);
            setSelectedFile(null);
        } else if (uploadMode === 'text' && value?.trim()) {
            onSubmit(null); // null file means use text
        }
    };

    const canSubmit = (uploadMode === 'text' && value?.trim()) || (uploadMode === 'file' && selectedFile);

    return (
        <div className="animate-fade-in">
            {/* Prompt Question */}
            {prompt && (
                <div className="mb-3 p-3 rounded-xl bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-100">
                    <div className="text-xs text-blue-600 font-semibold mb-1 flex items-center gap-1">
                        <Icon name="help-circle" className="h-3.5 w-3.5" />
                        Answer this:
                    </div>
                    <div className="text-sm text-blue-800">{prompt}</div>
                </div>
            )}

            {/* Mode Toggle */}
            <div className="flex gap-2 mb-3">
                <button
                    onClick={() => setUploadMode('text')}
                    className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-all flex items-center justify-center gap-2 ${uploadMode === 'text' ? 'bg-blue-600 text-white shadow-md' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
                >
                    <Icon name="type" className="h-4 w-4" />
                    Type Answer
                </button>
                <button
                    onClick={() => setUploadMode('file')}
                    className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-all flex items-center justify-center gap-2 ${uploadMode === 'file' ? 'bg-blue-600 text-white shadow-md' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
                >
                    <Icon name="upload" className="h-4 w-4" />
                    Upload File
                </button>
            </div>

            {/* Text Input Mode */}
            {uploadMode === 'text' && (
                <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
                    <textarea
                        value={value}
                        onChange={(e) => onChange(e.target.value)}
                        placeholder={`Enter information about ${displayName}...`}
                        className="w-full min-h-[100px] px-4 py-3 text-sm focus:outline-none resize-y border-none"
                        disabled={isLoading}
                    />
                </div>
            )}

            {/* File Upload Mode */}
            {uploadMode === 'file' && (
                <div
                    onClick={() => fileInputRef.current?.click()}
                    className={`rounded-xl border-2 border-dashed p-6 text-center cursor-pointer transition-all ${selectedFile ? 'border-green-300 bg-green-50' : 'border-gray-300 hover:border-blue-400 hover:bg-blue-50'}`}
                >
                    <input
                        ref={fileInputRef}
                        type="file"
                        onChange={handleFileSelect}
                        className="hidden"
                        accept=".pdf,.doc,.docx,.txt,.md,.csv,.json"
                    />
                    {selectedFile ? (
                        <div className="flex items-center justify-center gap-3">
                            <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
                                <Icon name="file-text" className="h-5 w-5 text-green-600" />
                            </div>
                            <div className="text-left">
                                <div className="font-medium text-green-800">{selectedFile.name}</div>
                                <div className="text-xs text-green-600">{(selectedFile.size / 1024).toFixed(1)} KB</div>
                            </div>
                            <button
                                onClick={(e) => { e.stopPropagation(); setSelectedFile(null); }}
                                className="p-1 hover:bg-green-200 rounded-full"
                            >
                                <Icon name="x" className="h-4 w-4 text-green-700" />
                            </button>
                        </div>
                    ) : (
                        <>
                            <Icon name="upload-cloud" className="h-8 w-8 text-gray-400 mx-auto mb-2" />
                            <div className="text-sm text-gray-600">Click to upload or drag & drop</div>
                            <div className="text-xs text-gray-400 mt-1">PDF, DOC, TXT, CSV (max 10MB)</div>
                        </>
                    )}
                </div>
            )}

            {/* Footer with Submit */}
            <div className="flex items-center justify-between mt-3">
                <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-green-600">+{expectedImprovement}%</span>
                    <span className="text-xs text-gray-500">score improvement</span>
                </div>
                <button
                    onClick={handleSubmit}
                    disabled={!canSubmit || isLoading}
                    className="h-10 px-5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-sm font-semibold hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 shadow-md hover:shadow-lg transition-all"
                >
                    {isLoading ? (
                        <>
                            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                            </svg>
                            Saving...
                        </>
                    ) : (
                        <>
                            <Icon name="check" className="h-4 w-4" />
                            Save & Improve
                        </>
                    )}
                </button>
            </div>

            {/* Keywords hint (collapsed) */}
            {detectionKeywords?.length > 0 && (
                <details className="mt-3 text-xs">
                    <summary className="cursor-pointer text-gray-400 hover:text-gray-600">
                        Keywords we search for...
                    </summary>
                    <div className="mt-1 flex flex-wrap gap-1">
                        {detectionKeywords.slice(0, 8).map((kw, i) => (
                            <span key={i} className="px-2 py-0.5 bg-gray-100 text-gray-500 rounded">{kw}</span>
                        ))}
                    </div>
                </details>
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
