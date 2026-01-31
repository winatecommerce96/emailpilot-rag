/**
 * Meeting Intelligence Tool - Redesigned Layout
 *
 * New layout structure:
 * - Top bar: Client selector + Connection status
 * - Action panel: Connect/Scan controls in a horizontal step layout
 * - Main content: Search + Results (full width for better space utilization)
 */

import { Icon, Card, CardHeader, CardTitle, CardContent, Button, Badge, Skeleton } from './ui.jsx';
import {
    useCalendarConnect,
    ConnectionStatus,
    GoogleSignInButton,
    ScanControls,
    MeetingSearch
} from './CalendarConnect.jsx';

const { useState, useEffect } = React;

/**
 * Compact Client Selector - Inline style for top bar
 */
function ClientSelector({ value, onChange, clients, loading, onRefresh }) {
    return (
        <div className="relative inline-flex items-center">
            {loading ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <div className="h-4 w-4 rounded-full border-2 border-primary border-t-transparent animate-spin" />
                    <span>Loading...</span>
                </div>
            ) : (
                <>
                    <Icon name="building-2" className="absolute left-3 h-4 w-4 text-muted-foreground pointer-events-none z-10" />
                    <select
                        value={value}
                        onChange={(e) => onChange(e.target.value)}
                        className="h-9 pl-9 pr-8 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring appearance-none cursor-pointer min-w-[200px]"
                    >
                        <option value="">Select client...</option>
                        {clients.map(c => (
                            <option key={c.client_id} value={c.client_id}>
                                {c.name || c.client_id}
                            </option>
                        ))}
                    </select>
                    <Icon name="chevron-down" className="absolute right-2 h-4 w-4 text-muted-foreground pointer-events-none" />
                </>
            )}
            {onRefresh && !loading && (
                <button
                    onClick={onRefresh}
                    className="ml-2 p-1.5 hover:bg-accent rounded-md text-muted-foreground hover:text-foreground transition-colors"
                    title="Refresh clients"
                >
                    <Icon name="refresh-cw" className="h-4 w-4" />
                </button>
            )}
        </div>
    );
}

/**
 * Step Indicator - Visual progress through workflow
 */
function StepIndicator({ step, label, active, completed, icon }) {
    return (
        <div className={`flex items-center gap-2 ${active ? 'text-primary' : completed ? 'text-success' : 'text-muted-foreground'}`}>
            <div className={`
                flex items-center justify-center w-8 h-8 rounded-full border-2 transition-colors
                ${active ? 'border-primary bg-primary/10' : completed ? 'border-success bg-success/10' : 'border-muted-foreground/30 bg-muted/50'}
            `}>
                {completed ? (
                    <Icon name="check" className="h-4 w-4" />
                ) : (
                    <Icon name={icon} className="h-4 w-4" />
                )}
            </div>
            <span className={`text-sm font-medium ${active ? '' : 'opacity-70'}`}>{label}</span>
        </div>
    );
}

/**
 * How It Works Panel - Moved to collapsible for cleaner UI
 */
function HowItWorks() {
    return (
        <details className="group">
            <summary className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer hover:text-foreground transition-colors">
                <Icon name="info" className="h-4 w-4" />
                How it works
                <Icon name="chevron-right" className="h-4 w-4 group-open:rotate-90 transition-transform" />
            </summary>
            <div className="mt-3 pl-6 space-y-2 text-sm text-muted-foreground">
                <p><strong>1.</strong> Connect your Google Calendar with read-only access.</p>
                <p><strong>2.</strong> We scan past meetings with external guests.</p>
                <p><strong>3.</strong> Gemini analyzes transcripts for strategic signals.</p>
                <p><strong>4.</strong> Insights are saved to the RAG Knowledge Base for search.</p>
            </div>
        </details>
    );
}

export function MeetingIntelligence() {
    const [selectedClient, setSelectedClient] = useState('');
    const [clients, setClients] = useState([]);
    const [clientsLoading, setClientsLoading] = useState(true);

    // Use the calendar connect hook
    const calendar = useCalendarConnect({
        clientId: selectedClient,
        clients: clients,
        onConnect: (session) => console.log('Connected', session),
        onScanTriggered: () => console.log('Scan started')
    });

    // Load clients
    const fetchClients = async () => {
        setClientsLoading(true);
        try {
            const res = await fetch('/api/clients', { credentials: 'include' });
            const data = await res.json();
            setClients(data.clients || []);
        } catch (err) {
            console.error('Failed to load clients', err);
        } finally {
            setClientsLoading(false);
        }
    };

    useEffect(() => {
        fetchClients();
    }, []);

    // Determine current step
    const currentStep = !calendar.connected ? 1 : !selectedClient ? 2 : 3;

    return (
        <div className="container mx-auto px-4 py-6 max-w-6xl">
            {/* Header Row: Title + Client Selector + Connection Status */}
            <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 mb-6">
                <div className="flex items-center gap-3">
                    <div className="p-2.5 bg-blue-100 dark:bg-blue-900/20 rounded-lg text-blue-600 dark:text-blue-400">
                        <Icon name="calendar" className="h-6 w-6" />
                    </div>
                    <div>
                        <h1 className="text-xl font-bold">Meeting Intelligence</h1>
                        <p className="text-sm text-muted-foreground">
                            Harvest strategic insights from client meetings
                        </p>
                    </div>
                </div>

                <div className="flex items-center gap-4 flex-wrap">
                    <ClientSelector
                        value={selectedClient}
                        onChange={setSelectedClient}
                        clients={clients}
                        loading={clientsLoading}
                        onRefresh={fetchClients}
                    />
                    <div className="h-6 w-px bg-border hidden sm:block" />
                    <ConnectionStatus
                        connected={calendar.connected}
                        onDisconnect={calendar.handleDisconnect}
                    />
                </div>
            </div>

            {/* Step Progress Indicator */}
            <div className="flex items-center gap-8 mb-6 pb-6 border-b overflow-x-auto">
                <StepIndicator
                    step={1}
                    label="Connect Calendar"
                    icon="calendar"
                    active={currentStep === 1}
                    completed={calendar.connected}
                />
                <div className={`flex-1 h-0.5 max-w-[60px] ${calendar.connected ? 'bg-success' : 'bg-muted'}`} />
                <StepIndicator
                    step={2}
                    label="Select Client"
                    icon="building-2"
                    active={currentStep === 2}
                    completed={calendar.connected && selectedClient}
                />
                <div className={`flex-1 h-0.5 max-w-[60px] ${calendar.connected && selectedClient ? 'bg-success' : 'bg-muted'}`} />
                <StepIndicator
                    step={3}
                    label="Scan & Search"
                    icon="search"
                    active={currentStep === 3}
                    completed={false}
                />
            </div>

            {/* Main Content Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Left Column: Connection + Scan Controls */}
                <div className="lg:col-span-1 space-y-4">
                    {/* Connection Card */}
                    {!calendar.connected && (
                        <Card>
                            <CardHeader className="pb-3">
                                <CardTitle className="text-base flex items-center gap-2">
                                    <Icon name="calendar" className="h-4 w-4" />
                                    Connect Calendar
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <p className="text-sm text-muted-foreground">
                                    Connect your Google Calendar to scan meeting transcripts for strategic insights.
                                </p>
                                <GoogleSignInButton
                                    onConnect={calendar.onConnect}
                                    loading={calendar.loading}
                                    setLoading={calendar.setLoading}
                                />
                                <p className="text-xs text-muted-foreground">
                                    Grants read-only access to Calendar events and Drive files for transcript analysis.
                                </p>
                            </CardContent>
                        </Card>
                    )}

                    {/* Scan Controls Card */}
                    {calendar.connected && (
                        <Card>
                            <CardHeader className="pb-3">
                                <CardTitle className="text-base flex items-center gap-2">
                                    <Icon name="refresh-cw" className="h-4 w-4" />
                                    Scan Meetings
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <ScanControls
                                    clientId={selectedClient}
                                    clients={clients}
                                    connected={calendar.connected}
                                    onScanTriggered={() => console.log('Scan started')}
                                    scanStatus={calendar.scanStatus}
                                    setScanStatus={calendar.setScanStatus}
                                    initialScanState={calendar.initialScanState}
                                    checkScanStatus={calendar.checkScanStatus}
                                />
                            </CardContent>
                        </Card>
                    )}

                    {/* How It Works - Collapsible */}
                    <Card className="bg-muted/30 border-muted">
                        <CardContent className="pt-4 pb-4">
                            <HowItWorks />
                        </CardContent>
                    </Card>

                    {/* Stats Card - Only show when connected */}
                    {calendar.connected && calendar.initialScanState && (
                        <Card>
                            <CardContent className="pt-4">
                                <div className="grid grid-cols-2 gap-4 text-center">
                                    <div>
                                        <div className="text-2xl font-bold text-primary">
                                            {calendar.initialScanState.clients_scanned?.length || 0}
                                        </div>
                                        <div className="text-xs text-muted-foreground">Clients Scanned</div>
                                    </div>
                                    <div>
                                        <div className="text-2xl font-bold text-primary">
                                            {calendar.initialScanState.total_meetings_processed || '-'}
                                        </div>
                                        <div className="text-xs text-muted-foreground">Meetings Processed</div>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    )}
                </div>

                {/* Right Column: Search & Results (takes 2/3 width) */}
                <div className="lg:col-span-2">
                    <Card className="h-full min-h-[500px]">
                        <CardHeader className="pb-3">
                            <CardTitle className="text-base flex items-center gap-2">
                                <Icon name="search" className="h-4 w-4" />
                                Search Meeting Intelligence
                                {selectedClient && (
                                    <Badge variant="secondary" className="ml-2 text-xs font-normal">
                                        {clients.find(c => c.client_id === selectedClient)?.name || selectedClient}
                                    </Badge>
                                )}
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            {clientsLoading ? (
                                <div className="space-y-4">
                                    <Skeleton className="h-11 w-full" />
                                    <Skeleton className="h-24 w-full" />
                                    <Skeleton className="h-24 w-full" />
                                </div>
                            ) : (
                                <MeetingSearch
                                    clientId={selectedClient}
                                    clients={clients}
                                />
                            )}
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    );
}
