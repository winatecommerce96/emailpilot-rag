/**
 * Meeting Intelligence App Entry Point
 */
import { MeetingIntelligence } from './components/MeetingIntelligence.jsx';
import { ToastContainer } from './components/ui.jsx';
import { useToast } from './hooks/useRAG.js';

function App() {
    const toast = useToast();
    
    // Expose toast to global scope for non-React components if needed
    window.toast = toast;

    return (
        <div className="min-h-screen bg-background">
            <MeetingIntelligence />
            <ToastContainer toasts={toast.toasts} onRemove={toast.removeToast} />
        </div>
    );
}

const container = document.getElementById('root');
const root = ReactDOM.createRoot(container);
root.render(<App />);
