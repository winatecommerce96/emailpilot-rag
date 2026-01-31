/**
 * shadcn/ui-inspired UI Components
 * Modern, accessible, and customizable
 */

const { useState, useEffect, useRef, forwardRef } = React;

// ============================================================================
// ICON COMPONENT - Renders common Lucide icons as React SVGs
// ============================================================================
const ICON_PATHS = {
    'database': 'M3 3h18v18H3z M3 9h18 M3 15h18 M21 3v18 M3 3v18',
    'building-2': 'M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2 M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2 M10 6h4 M10 10h4 M10 14h4 M10 18h4',
    'chevron-down': 'm6 9 6 6 6-6',
    'chevron-left': 'm15 18-6-6 6-6',
    'chevron-right': 'm9 18 6-6-6-6',
    'check': 'M20 6 9 17l-5-5',
    'refresh-cw': 'M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8 M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16 M21 3v5h-5 M3 21v-5h5',
    'search': 'M19 19l-4-4m0-7A7 7 0 1 1 4 8a7 7 0 0 1 11 0z',
    'upload': 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4 M17 8l-5-5-5 5 M12 3v12',
    'upload-cloud': 'M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242 M12 12v9 M8 17l4-4 4 4',
    'file-text': 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M16 13H8 M16 17H8 M10 9H8',
    'folder-plus': 'M12 10v6 M9 13h6 M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z',
    'eye': 'M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z',
    'download': 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4 M7 10l5 5 5-5 M12 15V3',
    'trash-2': 'M3 6h18 M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6 M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2 M10 11v6 M14 11v6',
    'alert-circle': 'M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z M12 8v4 M12 16h.01',
    'alert-triangle': 'M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z M12 9v4 M12 17h.01',
    'x': 'M18 6 6 18 M6 6l12 12',
    'x-circle': 'M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z M15 9l-6 6 M9 9l6 6',
    'check-circle': 'M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z M9 12l2 2 4-4',
    'info': 'M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z M12 16v-4 M12 8h.01',
    'search-x': 'M19 19l-4-4 M13.5 8.5L10.5 11.5 M10.5 8.5l3 3 M5 11a6 6 0 1 0 12 0 6 6 0 0 0-12 0z',
    'sparkles': 'M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z M20 3v4 M22 5h-4 M4 17v2 M5 18H3',
    'image': 'M19 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2z M8.5 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z M21 15l-5-5L5 21',
    'file': 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6',
    'code': 'm8 18 4-12h4 M8 6l-4 6 4 6 M16 6l4 6-4 6',
    'braces': 'M8 3H7a2 2 0 0 0-2 2v5a2 2 0 0 1-2 2 2 2 0 0 1 2 2v5a2 2 0 0 0 2 2h1 M16 3h1a2 2 0 0 1 2 2v5a2 2 0 0 0 2 2 2 2 0 0 0-2 2v5a2 2 0 0 1-2 2h-1',
    'table': 'M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18',
    // Additional icons
    'inbox': 'M22 12h-6l-2 3h-4l-2-3H2 M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z',
    'library': 'M4 19.5A2.5 2.5 0 0 1 6.5 17H20 M4 4.5A2.5 2.5 0 0 1 6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15z',
    'user-x': 'M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2 M8.5 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z M18 8l5 5 M23 8l-5 5',
    'folder': 'M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z',
    'calendar': 'M19 4H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 0V2m-14 2V2m0 6h14',
    'plus': 'M12 5v14M5 12h14',
    'settings': 'M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.38a2 2 0 0 0-.73-2.73l-.15-.1a2 2 0 0 1-1-1.72v-.51a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z',
    'user': 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2 M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z',
    'grid': 'M3 3h7v7H3z M14 3h7v7h-7z M14 14h7v7h-7z M3 14h7v7H3z',
    'history': 'M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8 M3 3v5h5 M12 7v5l4 2',
    'clock': 'M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z M12 6v6l4 2',
    'zap': 'M13 2L3 14h9l-1 8 10-12h-9l1-8z',
    'text': 'M17 6.1H3 M21 12.1H3 M15.1 18H3',
    'bar-chart-3': 'M3 3v18h18 M18 17V9 M13 17V5 M8 17v-3',
    'bar-chart': 'M12 20V10 M18 20V4 M6 20v-4',
    'activity': 'M22 12h-4l-3 9L9 3l-3 9H2',
};

export function Icon({ name, className = '', size, ...props }) {
    const pathData = ICON_PATHS[name];

    if (!pathData) {
        console.warn(`Icon "${name}" not found`);
        return <span className={className} />;
    }

    return (
        <svg
            xmlns="http://www.w3.org/2000/svg"
            width={size || 24}
            height={size || 24}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={className}
            {...props}
        >
            <path d={pathData} />
        </svg>
    );
}

// ============================================================================
// BUTTON
// ============================================================================
export function Button({
    children,
    variant = 'default',
    size = 'default',
    disabled = false,
    loading = false,
    className = '',
    onClick,
    ...props
}) {
    const baseStyles = 'inline-flex items-center justify-center rounded-md font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50';

    const variants = {
        default: 'bg-primary text-primary-foreground hover:bg-primary/90',
        destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        outline: 'border border-input bg-background hover:bg-accent hover:text-accent-foreground',
        secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
        ghost: 'hover:bg-accent hover:text-accent-foreground',
        link: 'text-primary underline-offset-4 hover:underline',
        success: 'bg-success text-success-foreground hover:bg-success/90',
    };

    const sizes = {
        default: 'h-10 px-4 py-2',
        sm: 'h-9 rounded-md px-3 text-sm',
        lg: 'h-11 rounded-md px-8',
        icon: 'h-10 w-10',
    };

    return (
        <button
            type="button"
            className={`${baseStyles} ${variants[variant]} ${sizes[size]} ${className}`}
            disabled={disabled || loading}
            onClick={onClick}
            {...props}
        >
            {loading && (
                <svg className="mr-2 h-4 w-4 animate-spin" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
            )}
            {children}
        </button>
    );
}

// ============================================================================
// INPUT
// ============================================================================
export function Input({
    type = 'text',
    className = '',
    error = false,
    ...props
}) {
    const baseStyles = 'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50';
    const errorStyles = error ? 'border-destructive focus-visible:ring-destructive' : '';

    return (
        <input
            type={type}
            className={`${baseStyles} ${errorStyles} ${className}`}
            {...props}
        />
    );
}

// ============================================================================
// TEXTAREA
// ============================================================================
export function Textarea({ className = '', error = false, ...props }) {
    const baseStyles = 'flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50';
    const errorStyles = error ? 'border-destructive focus-visible:ring-destructive' : '';

    return (
        <textarea
            className={`${baseStyles} ${errorStyles} ${className}`}
            {...props}
        />
    );
}

// ============================================================================
// SELECT
// ============================================================================
export function Select({ children, className = '', ...props }) {
    const baseStyles = 'flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50';

    return (
        <select className={`${baseStyles} ${className}`} {...props}>
            {children}
        </select>
    );
}

// ============================================================================
// CARD
// ============================================================================
export function Card({ children, className = '', hover = false, ...props }) {
    const baseStyles = 'rounded-lg border bg-card text-card-foreground shadow-sm';
    const hoverStyles = hover ? 'card-hover cursor-pointer' : '';

    return (
        <div className={`${baseStyles} ${hoverStyles} ${className}`} {...props}>
            {children}
        </div>
    );
}

export function CardHeader({ children, className = '', ...props }) {
    return (
        <div className={`flex flex-col space-y-1.5 p-6 ${className}`} {...props}>
            {children}
        </div>
    );
}

export function CardTitle({ children, className = '', ...props }) {
    return (
        <h3 className={`text-2xl font-semibold leading-none tracking-tight ${className}`} {...props}>
            {children}
        </h3>
    );
}

export function CardDescription({ children, className = '', ...props }) {
    return (
        <p className={`text-sm text-muted-foreground ${className}`} {...props}>
            {children}
        </p>
    );
}

export function CardContent({ children, className = '', ...props }) {
    return (
        <div className={`p-6 pt-0 ${className}`} {...props}>
            {children}
        </div>
    );
}

export function CardFooter({ children, className = '', ...props }) {
    return (
        <div className={`flex items-center p-6 pt-0 ${className}`} {...props}>
            {children}
        </div>
    );
}

// ============================================================================
// BADGE
// ============================================================================
export function Badge({ children, variant = 'default', className = '', ...props }) {
    const variants = {
        default: 'bg-primary text-primary-foreground hover:bg-primary/80',
        secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
        destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/80',
        outline: 'border border-input bg-background hover:bg-accent',
        success: 'bg-success text-success-foreground',
    };

    return (
        <div
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors ${variants[variant]} ${className}`}
            {...props}
        >
            {children}
        </div>
    );
}

// ============================================================================
// TABS
// ============================================================================
export function Tabs({ children, value, onValueChange, className = '' }) {
    return (
        <div className={`${className}`} data-value={value}>
            {React.Children.map(children, child => {
                if (React.isValidElement(child)) {
                    return React.cloneElement(child, { activeTab: value, onTabChange: onValueChange });
                }
                return child;
            })}
        </div>
    );
}

export function TabsList({ children, className = '', activeTab, onTabChange }) {
    return (
        <div className={`inline-flex h-10 items-center justify-center rounded-md bg-muted p-1 text-muted-foreground ${className}`}>
            {React.Children.map(children, child => {
                if (React.isValidElement(child)) {
                    return React.cloneElement(child, { activeTab, onTabChange });
                }
                return child;
            })}
        </div>
    );
}

export function TabsTrigger({ children, value, className = '', activeTab, onTabChange }) {
    const isActive = activeTab === value;

    return (
        <button
            className={`inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 ${
                isActive
                    ? 'bg-background text-foreground shadow-sm'
                    : 'hover:bg-background/50 hover:text-foreground'
            } ${className}`}
            onClick={() => onTabChange?.(value)}
        >
            {children}
        </button>
    );
}

export function TabsContent({ children, value, className = '', activeTab }) {
    if (activeTab !== value) return null;

    return (
        <div className={`mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 animate-fade-in ${className}`}>
            {children}
        </div>
    );
}

// ============================================================================
// PROGRESS
// ============================================================================
export function Progress({ value = 0, className = '', showLabel = false }) {
    return (
        <div className={`relative ${className}`}>
            <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
                <div
                    className="h-full bg-primary transition-all progress-bar"
                    style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
                />
            </div>
            {showLabel && (
                <span className="absolute right-0 top-3 text-xs text-muted-foreground">
                    {Math.round(value)}%
                </span>
            )}
        </div>
    );
}

// ============================================================================
// SKELETON
// ============================================================================
export function Skeleton({ className = '', ...props }) {
    return (
        <div
            className={`skeleton rounded-md bg-muted ${className}`}
            {...props}
        />
    );
}

// ============================================================================
// ALERT
// ============================================================================
export function Alert({ children, variant = 'default', className = '', ...props }) {
    const variants = {
        default: 'bg-background border',
        destructive: 'border-destructive/50 text-destructive bg-destructive/10',
        success: 'border-success/50 text-success bg-success/10',
        warning: 'border-yellow-500/50 text-yellow-700 bg-yellow-50',
    };

    return (
        <div
            role="alert"
            className={`relative w-full rounded-lg border p-4 ${variants[variant]} ${className}`}
            {...props}
        >
            {children}
        </div>
    );
}

export function AlertTitle({ children, className = '', ...props }) {
    return (
        <h5 className={`mb-1 font-medium leading-none tracking-tight ${className}`} {...props}>
            {children}
        </h5>
    );
}

export function AlertDescription({ children, className = '', ...props }) {
    return (
        <div className={`text-sm [&_p]:leading-relaxed ${className}`} {...props}>
            {children}
        </div>
    );
}

// ============================================================================
// DIALOG / MODAL
// ============================================================================
export function Dialog({ open, onOpenChange, children }) {
    useEffect(() => {
        if (open) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = '';
        }
        return () => {
            document.body.style.overflow = '';
        };
    }, [open]);

    if (!open) return null;

    return (
        <div className="fixed inset-0 z-50">
            <div
                className="fixed inset-0 bg-black/80 animate-fade-in"
                onClick={() => onOpenChange?.(false)}
            />
            <div className="fixed inset-0 flex items-center justify-center p-4">
                {children}
            </div>
        </div>
    );
}

export function DialogContent({ children, className = '', ...props }) {
    return (
        <div
            className={`relative bg-background rounded-lg shadow-lg max-w-lg w-full max-h-[85vh] overflow-auto animate-fade-in ${className}`}
            onClick={e => e.stopPropagation()}
            {...props}
        >
            {children}
        </div>
    );
}

export function DialogHeader({ children, className = '', ...props }) {
    return (
        <div className={`flex flex-col space-y-1.5 p-6 ${className}`} {...props}>
            {children}
        </div>
    );
}

export function DialogTitle({ children, className = '', ...props }) {
    return (
        <h2 className={`text-lg font-semibold leading-none tracking-tight ${className}`} {...props}>
            {children}
        </h2>
    );
}

export function DialogDescription({ children, className = '', ...props }) {
    return (
        <p className={`text-sm text-muted-foreground ${className}`} {...props}>
            {children}
        </p>
    );
}

export function DialogFooter({ children, className = '', ...props }) {
    return (
        <div className={`flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2 p-6 pt-0 ${className}`} {...props}>
            {children}
        </div>
    );
}

// ============================================================================
// TOAST
// ============================================================================
export function Toast({ message, type = 'info', onClose }) {
    const types = {
        info: 'bg-background border',
        success: 'bg-success/10 border-success/50 text-success',
        error: 'bg-destructive/10 border-destructive/50 text-destructive',
        warning: 'bg-yellow-50 border-yellow-500/50 text-yellow-700',
    };

    const icons = {
        info: 'info',
        success: 'check-circle',
        error: 'x-circle',
        warning: 'alert-triangle',
    };

    return (
        <div className={`flex items-center gap-3 rounded-lg border p-4 shadow-lg toast-enter ${types[type]}`}>
            <Icon name={icons[type]} className="h-5 w-5" />
            <span className="text-sm font-medium">{message}</span>
            <button
                onClick={onClose}
                className="ml-auto rounded-md p-1 hover:bg-muted"
            >
                <Icon name="x" className="h-4 w-4" />
            </button>
        </div>
    );
}

export function ToastContainer({ toasts, onRemove }) {
    return (
        <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
            {toasts.map(toast => (
                <Toast
                    key={toast.id}
                    message={toast.message}
                    type={toast.type}
                    onClose={() => onRemove(toast.id)}
                />
            ))}
        </div>
    );
}

// ============================================================================
// EMPTY STATE
// ============================================================================
export function EmptyState({ icon = 'inbox', title, description, action }) {
    return (
        <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="rounded-full bg-muted p-4 mb-4">
                <Icon name={icon} className="h-8 w-8 text-muted-foreground" />
            </div>
            <h3 className="text-lg font-semibold">{title}</h3>
            {description && (
                <p className="text-sm text-muted-foreground mt-1 max-w-sm">{description}</p>
            )}
            {action && <div className="mt-4">{action}</div>}
        </div>
    );
}

// ============================================================================
// SPINNER
// ============================================================================
export function Spinner({ size = 'default', className = '' }) {
    const sizes = {
        sm: 'h-4 w-4',
        default: 'h-6 w-6',
        lg: 'h-8 w-8',
    };

    return (
        <svg
            className={`animate-spin ${sizes[size]} ${className}`}
            viewBox="0 0 24 24"
            fill="none"
        >
            <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
            />
            <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
        </svg>
    );
}

export default {
    Icon,
    Button,
    Input,
    Textarea,
    Select,
    Card,
    CardHeader,
    CardTitle,
    CardDescription,
    CardContent,
    CardFooter,
    Badge,
    Tabs,
    TabsList,
    TabsTrigger,
    TabsContent,
    Progress,
    Skeleton,
    Alert,
    AlertTitle,
    AlertDescription,
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
    Toast,
    ToastContainer,
    EmptyState,
    Spinner,
};
