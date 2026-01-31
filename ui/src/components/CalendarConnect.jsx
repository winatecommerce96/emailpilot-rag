/**
 * Calendar Connect Component - Redesigned
 * Split into focused sub-components for better layout flexibility
 */

import { Icon, Button, Alert, AlertTitle, Input, Spinner, Card, CardHeader, CardTitle, CardContent, Badge } from './ui.jsx';
import { useRAGSearch } from '../hooks/useRAG.js';

const { useState, useEffect, useCallback } = React;

/**
 * Connection Status Badge - Shows connected/disconnected state
 */
export function ConnectionStatus({ connected, onDisconnect }) {
    if (!connected) {
        return (
            <div className="flex items-center gap-2 text-muted-foreground">
                <div className="h-2 w-2 rounded-full bg-gray-300" />
                <span className="text-sm">Not connected</span>
            </div>
        );
    }

    return (
        <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-success">
                <div className="h-2 w-2 rounded-full bg-success animate-pulse" />
                <span className="text-sm font-medium">Calendar Connected</span>
            </div>
            <button
                onClick={onDisconnect}
                className="text-xs text-muted-foreground hover:text-destructive transition-colors underline decoration-dotted"
            >
                Disconnect
            </button>
        </div>
    );
}

/**
 * Google Sign-In Button - Standalone OAuth trigger
 */
export function GoogleSignInButton({ onConnect, loading, setLoading }) {
    const handleConnect = async () => {
        setLoading(true);
        try {
            const response = await fetch('/api/meeting/auth', { credentials: 'include' });
            const data = await response.json();
            if (data.auth_url) {
                window.location.href = data.auth_url;
            }
        } catch (error) {
            console.error('Auth start failed:', error);
        } finally {
            setLoading(false);
        }
    };

    return (
        <button
            onClick={handleConnect}
            disabled={loading}
            className="gsi-material-button"
            style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                height: '44px',
                padding: '0 16px',
                border: '1px solid #dadce0',
                borderRadius: '6px',
                backgroundColor: '#fff',
                fontFamily: "'Google Sans', Roboto, Arial, sans-serif",
                fontSize: '14px',
                fontWeight: 500,
                color: '#3c4043',
                cursor: loading ? 'wait' : 'pointer',
                transition: 'background-color 0.2s, box-shadow 0.2s',
                boxShadow: '0 1px 2px 0 rgba(60, 64, 67, 0.3), 0 1px 3px 1px rgba(60, 64, 67, 0.15)',
                opacity: loading ? 0.7 : 1
            }}
            onMouseOver={(e) => { if (!loading) e.currentTarget.style.boxShadow = '0 1px 3px 0 rgba(60, 64, 67, 0.3), 0 4px 8px 3px rgba(60, 64, 67, 0.15)'; }}
            onMouseOut={(e) => { e.currentTarget.style.boxShadow = '0 1px 2px 0 rgba(60, 64, 67, 0.3), 0 1px 3px 1px rgba(60, 64, 67, 0.15)'; }}
        >
            {loading ? (
                <svg className="animate-spin h-5 w-5 mr-3" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
            ) : (
                <svg width="18" height="18" viewBox="0 0 18 18" style={{ marginRight: '10px' }}>
                    <path fill="#4285F4" d="M16.51 8H8.98v3h4.3c-.18 1-.74 1.48-1.6 2.04v2.01h2.6a7.8 7.8 0 0 0 2.38-5.88c0-.57-.05-.66-.15-1.18z"/>
                    <path fill="#34A853" d="M8.98 17c2.16 0 3.97-.72 5.3-1.94l-2.6-2a4.8 4.8 0 0 1-7.18-2.54H1.83v2.07A8 8 0 0 0 8.98 17z"/>
                    <path fill="#FBBC05" d="M4.5 10.52a4.8 4.8 0 0 1 0-3.04V5.41H1.83a8 8 0 0 0 0 7.18l2.67-2.07z"/>
                    <path fill="#EA4335" d="M8.98 4.18c1.17 0 2.23.4 3.06 1.2l2.3-2.3A8 8 0 0 0 1.83 5.4L4.5 7.49a4.77 4.77 0 0 1 4.48-3.3z"/>
                </svg>
            )}
            <span>Sign in with Google</span>
        </button>
    );
}

/**
 * Scan Controls Panel - Handles Quick Scan and Backfill actions
 */
export function ScanControls({
    clientId,
    clients = [],
    connected,
    onScanTriggered,
    scanStatus,
    setScanStatus,
    initialScanState,
    checkScanStatus
}) {
    const [loading, setLoading] = useState(false);
    const [backfillLoading, setBackfillLoading] = useState(false);
    const [scanConfig, setScanConfig] = useState({
        backfill: false,
        domain: ''
    });

    const handleScan = async () => {
        if (!clientId) return;

        const session = localStorage.getItem('meeting_session');
        if (!session) return;

        setLoading(true);
        setScanStatus(null);

        const lookback = scanConfig.backfill ? 168 : 24;
        let url = `/api/meeting/scan/${clientId}?session_id=${session}&lookback_hours=${lookback}`;
        if (scanConfig.domain) {
            url += `&client_domain=${encodeURIComponent(scanConfig.domain)}`;
        }

        try {
            const response = await fetch(url, {
                method: 'POST',
                credentials: 'include'
            });

            if (response.ok) {
                setScanStatus({ type: 'success', message: `Scanning past ${lookback}h ${scanConfig.domain ? 'for @' + scanConfig.domain : ''}...` });
                if (onScanTriggered) onScanTriggered();
            } else {
                throw new Error('Scan failed to start');
            }
        } catch (error) {
            console.error('Scan trigger failed:', error);
            setScanStatus({ type: 'error', message: 'Failed to trigger scan' });
        } finally {
            setLoading(false);
        }
    };

    const handleBackfill = async () => {
        const session = localStorage.getItem('meeting_session');
        if (!session || !clients || clients.length === 0) return;

        setBackfillLoading(true);
        setScanStatus(null);

        const clientIds = clients.map(c => c.client_id);

        try {
            const res = await fetch(`/api/meeting/initial-scan?session_id=${session}`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ client_ids: clientIds, force: true })
            });

            if (res.ok) {
                const data = await res.json();
                setScanStatus({
                    type: 'success',
                    message: `Backfill started: Scanning 60 days for ${clientIds.length} clients...`
                });
                setTimeout(() => checkScanStatus(session), 2000);
                if (onScanTriggered) onScanTriggered();
            } else {
                const err = await res.json();
                throw new Error(err.detail || 'Backfill failed');
            }
        } catch (error) {
            console.error('Backfill failed:', error);
            setScanStatus({ type: 'error', message: error.message || 'Failed to start backfill' });
        } finally {
            setBackfillLoading(false);
        }
    };

    if (!connected) {
        return (
            <div className="flex items-center justify-center py-6 text-muted-foreground text-sm">
                <Icon name="calendar" className="h-5 w-5 mr-2 opacity-50" />
                Connect your calendar to enable scanning
            </div>
        );
    }

    const selectedClientName = clients.find(c => c.client_id === clientId)?.name || clientId;

    return (
        <div className="space-y-4">
            {/* Initial Scan Progress */}
            {initialScanState && (
                <div className="p-3 bg-muted/50 rounded-lg text-sm">
                    <div className="flex items-center justify-between mb-1">
                        <span className="font-medium">Initial Scan (60 days)</span>
                        {initialScanState.initial_scan_completed ? (
                            <Badge variant="success" className="text-xs">
                                <Icon name="check" className="h-3 w-3 mr-1" /> Complete
                            </Badge>
                        ) : (
                            <Badge variant="secondary" className="text-xs">
                                <span className="h-2 w-2 bg-blue-500 rounded-full animate-pulse mr-1.5" /> In Progress
                            </Badge>
                        )}
                    </div>
                    {initialScanState.clients_scanned?.length > 0 && (
                        <p className="text-xs text-muted-foreground">
                            Scanned: {initialScanState.clients_scanned.join(', ')}
                        </p>
                    )}
                    {initialScanState.last_scan_at && (
                        <p className="text-xs text-muted-foreground">
                            Last: {new Date(initialScanState.last_scan_at).toLocaleDateString()}
                        </p>
                    )}
                </div>
            )}

            {/* Scan Actions */}
            <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                    <Button
                        onClick={handleScan}
                        loading={loading}
                        disabled={!clientId}
                        variant="outline"
                        className="w-full h-12"
                    >
                        <Icon name="refresh-cw" className="h-4 w-4 mr-2" />
                        Quick Scan
                    </Button>
                    <p className="text-[10px] text-muted-foreground text-center">
                        Last 24h for {clientId ? selectedClientName : 'selected client'}
                    </p>
                </div>
                <div className="space-y-2">
                    <Button
                        onClick={handleBackfill}
                        loading={backfillLoading}
                        disabled={!clients || clients.length === 0}
                        variant="secondary"
                        className="w-full h-12"
                    >
                        <Icon name="history" className="h-4 w-4 mr-2" />
                        Backfill All
                    </Button>
                    <p className="text-[10px] text-muted-foreground text-center">
                        60 days for all {clients?.length || 0} clients
                    </p>
                </div>
            </div>

            {/* Advanced Options - Collapsible */}
            <details className="group">
                <summary className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer hover:text-foreground transition-colors">
                    <Icon name="settings" className="h-3 w-3" />
                    Advanced Options
                    <Icon name="chevron-right" className="h-3 w-3 group-open:rotate-90 transition-transform" />
                </summary>
                <div className="mt-3 p-3 bg-muted/30 rounded-lg space-y-3">
                    <div>
                        <label className="text-xs font-medium text-muted-foreground block mb-1">Filter by Domain</label>
                        <Input
                            value={scanConfig.domain}
                            onChange={(e) => setScanConfig(prev => ({...prev, domain: e.target.value}))}
                            placeholder="e.g. roguecreamery.com"
                            className="h-8 text-sm"
                        />
                        <p className="text-[10px] text-muted-foreground mt-1">Only scan meetings with attendees from this domain</p>
                    </div>

                    <div className="flex items-center gap-2">
                        <input
                            type="checkbox"
                            id="backfill-scan-option"
                            checked={scanConfig.backfill}
                            onChange={(e) => setScanConfig(prev => ({...prev, backfill: e.target.checked}))}
                            className="rounded border-gray-300 text-primary focus:ring-primary"
                        />
                        <label htmlFor="backfill-scan-option" className="text-xs cursor-pointer select-none">
                            Extend Quick Scan to 7 days (default: 24h)
                        </label>
                    </div>
                </div>
            </details>

            {/* Status Alert */}
            {scanStatus && (
                <Alert variant={scanStatus.type === 'error' ? 'destructive' : 'success'} className="py-2 px-3 text-sm">
                    <AlertTitle className="font-medium mb-0 flex items-center gap-2">
                        <Icon name={scanStatus.type === 'error' ? 'alert-triangle' : 'check'} className="h-4 w-4" />
                        {scanStatus.message}
                    </AlertTitle>
                </Alert>
            )}
        </div>
    );
}

/**
 * Meeting Intelligence Search - Query interface for meeting intel
 */
export function MeetingSearch({ clientId, clients = [] }) {
    const [query, setQuery] = useState('');
    const search = useRAGSearch(clientId);

    const handleQuery = (e) => {
        e.preventDefault();
        if (query.trim()) {
            search.search(query, 'STRATEGY', 5);
        }
    };

    const selectedClientName = clients.find(c => c.client_id === clientId)?.name || clientId;

    return (
        <div className="space-y-4">
            <form onSubmit={handleQuery} className="flex gap-3">
                <div className="relative flex-1">
                    <Icon name="search" className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="Search meeting intelligence... (e.g. 'inventory issues', 'Q4 promotions')"
                        className="pl-10 h-11"
                        disabled={!clientId}
                    />
                </div>
                <Button
                    type="submit"
                    disabled={!query.trim() || !clientId || search.loading}
                    className="h-11 px-6"
                >
                    {search.loading ? <Spinner size="sm" /> : 'Search'}
                </Button>
            </form>

            {/* Results */}
            {search.results.length > 0 && (
                <div className="space-y-3">
                    <div className="flex items-center justify-between">
                        <h4 className="text-sm font-medium">
                            {search.results.length} result{search.results.length !== 1 ? 's' : ''} for "{query}"
                        </h4>
                        <button
                            onClick={() => { setQuery(''); search.clear(); }}
                            className="text-xs text-muted-foreground hover:text-foreground"
                        >
                            Clear
                        </button>
                    </div>
                    {search.results.map((result, i) => (
                        <Card key={i} className="overflow-hidden">
                            <CardContent className="p-4">
                                <div className="flex items-start justify-between gap-4 mb-2">
                                    <div className="flex items-center gap-2">
                                        <Icon name="file-text" className="h-4 w-4 text-muted-foreground" />
                                        <span className="font-medium text-sm">{result.metadata?.title || 'Meeting Note'}</span>
                                    </div>
                                    <Badge variant="secondary" className="text-xs shrink-0">
                                        {Math.round(result.relevance_score * 100)}% match
                                    </Badge>
                                </div>
                                <p className="text-sm text-muted-foreground line-clamp-3">{result.content}</p>
                                {result.metadata?.date && (
                                    <p className="text-xs text-muted-foreground mt-2">
                                        <Icon name="calendar" className="h-3 w-3 inline mr-1" />
                                        {new Date(result.metadata.date).toLocaleDateString()}
                                    </p>
                                )}
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}

            {search.results.length === 0 && query && !search.loading && search.error === null && (
                <div className="text-center py-8 text-muted-foreground">
                    <Icon name="search-x" className="h-8 w-8 mx-auto mb-2 opacity-50" />
                    <p className="text-sm">No meeting intelligence found for "{query}"</p>
                    <p className="text-xs mt-1">Try different keywords or run a scan to gather more data</p>
                </div>
            )}

            {!clientId && (
                <div className="text-center py-8 text-muted-foreground">
                    <Icon name="user-x" className="h-8 w-8 mx-auto mb-2 opacity-50" />
                    <p className="text-sm">Select a client to search their meeting intelligence</p>
                </div>
            )}

            {clientId && !query && search.results.length === 0 && (
                <div className="text-center py-8 text-muted-foreground">
                    <Icon name="sparkles" className="h-8 w-8 mx-auto mb-2 opacity-50" />
                    <p className="text-sm">Search {selectedClientName}'s meeting intelligence</p>
                    <p className="text-xs mt-1">Find product launches, inventory issues, marketing themes, and more</p>
                </div>
            )}
        </div>
    );
}

/**
 * Main CalendarConnect Component - Now a controller/orchestrator
 * This maintains backward compatibility while allowing individual components to be used
 */
export function CalendarConnect({ clientId, clients = [], onConnect, onScanTriggered }) {
    const [loading, setLoading] = useState(false);
    const [connected, setConnected] = useState(false);
    const [scanStatus, setScanStatus] = useState(null);
    const [initialScanState, setInitialScanState] = useState(null);

    const checkScanStatus = async (session) => {
        try {
            const res = await fetch(`/api/meeting/scan-status?session_id=${session}`, { credentials: 'include' });
            if (res.ok) {
                const data = await res.json();
                setInitialScanState(data);
            }
        } catch (err) {
            console.error('Failed to check scan status:', err);
        }
    };

    const triggerInitialScan = async (session, clientList) => {
        if (!clientList || clientList.length === 0) return;

        const clientIds = clientList.map(c => c.client_id);
        try {
            const res = await fetch(`/api/meeting/initial-scan?session_id=${session}`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ client_ids: clientIds })
            });

            if (res.ok) {
                const data = await res.json();
                setScanStatus({
                    type: 'success',
                    message: data.status === 'already_completed'
                        ? 'Initial scan already completed'
                        : `Started 60-day scan for ${clientIds.length} clients...`
                });
                if (onScanTriggered) onScanTriggered();
            }
        } catch (err) {
            console.error('Initial scan failed:', err);
        }
    };

    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const session = params.get('meeting_session');

        if (session) {
            localStorage.setItem('meeting_session', session);
            setConnected(true);
            window.history.replaceState({}, document.title, window.location.pathname);
            if (onConnect) onConnect(session);
            triggerInitialScan(session, clients);
        } else if (localStorage.getItem('meeting_session')) {
            setConnected(true);
            checkScanStatus(localStorage.getItem('meeting_session'));
        }
    }, [onConnect, clients]);

    const handleDisconnect = () => {
        localStorage.removeItem('meeting_session');
        setConnected(false);
        setScanStatus(null);
        setInitialScanState(null);
    };

    // Expose state and handlers for parent components
    return {
        connected,
        loading,
        setLoading,
        scanStatus,
        setScanStatus,
        initialScanState,
        checkScanStatus,
        handleDisconnect,
        // Render methods for flexible composition
        renderConnectionStatus: () => (
            <ConnectionStatus connected={connected} onDisconnect={handleDisconnect} />
        ),
        renderSignInButton: () => (
            <GoogleSignInButton onConnect={onConnect} loading={loading} setLoading={setLoading} />
        ),
        renderScanControls: () => (
            <ScanControls
                clientId={clientId}
                clients={clients}
                connected={connected}
                onScanTriggered={onScanTriggered}
                scanStatus={scanStatus}
                setScanStatus={setScanStatus}
                initialScanState={initialScanState}
                checkScanStatus={checkScanStatus}
            />
        ),
        renderSearch: () => (
            <MeetingSearch clientId={clientId} clients={clients} />
        )
    };
}

/**
 * Hook version for more flexible usage in the new layout
 */
export function useCalendarConnect({ clientId, clients = [], onConnect, onScanTriggered }) {
    const [loading, setLoading] = useState(false);
    const [connected, setConnected] = useState(false);
    const [scanStatus, setScanStatus] = useState(null);
    const [initialScanState, setInitialScanState] = useState(null);

    const checkScanStatus = useCallback(async (session) => {
        try {
            const res = await fetch(`/api/meeting/scan-status?session_id=${session}`, { credentials: 'include' });
            if (res.ok) {
                const data = await res.json();
                setInitialScanState(data);
            }
        } catch (err) {
            console.error('Failed to check scan status:', err);
        }
    }, []);

    const triggerInitialScan = useCallback(async (session, clientList) => {
        if (!clientList || clientList.length === 0) return;

        const clientIds = clientList.map(c => c.client_id);
        try {
            const res = await fetch(`/api/meeting/initial-scan?session_id=${session}`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ client_ids: clientIds })
            });

            if (res.ok) {
                const data = await res.json();
                setScanStatus({
                    type: 'success',
                    message: data.status === 'already_completed'
                        ? 'Initial scan already completed'
                        : `Started 60-day scan for ${clientIds.length} clients...`
                });
                if (onScanTriggered) onScanTriggered();
            }
        } catch (err) {
            console.error('Initial scan failed:', err);
        }
    }, [onScanTriggered]);

    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const session = params.get('meeting_session');

        if (session) {
            localStorage.setItem('meeting_session', session);
            setConnected(true);
            window.history.replaceState({}, document.title, window.location.pathname);
            if (onConnect) onConnect(session);
            triggerInitialScan(session, clients);
        } else if (localStorage.getItem('meeting_session')) {
            setConnected(true);
            checkScanStatus(localStorage.getItem('meeting_session'));
        }
    }, [onConnect, clients, triggerInitialScan, checkScanStatus]);

    const handleDisconnect = useCallback(() => {
        localStorage.removeItem('meeting_session');
        setConnected(false);
        setScanStatus(null);
        setInitialScanState(null);
    }, []);

    return {
        connected,
        loading,
        setLoading,
        scanStatus,
        setScanStatus,
        initialScanState,
        checkScanStatus,
        handleDisconnect,
        clientId,
        clients
    };
}
