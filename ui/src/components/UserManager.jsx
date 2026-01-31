/**
 * User Manager Component
 * Handles user settings, profile, and integrations
 */

import { Icon, Button, Card, CardHeader, CardTitle, CardDescription, CardContent, Badge, Alert, AlertTitle } from './ui.jsx';
import { CalendarConnect } from './CalendarConnect.jsx';

const { useState, useEffect } = React;

export function UserManager({ clientId }) {
    // We can access user info from window.Clerk if available or local storage
    const [user, setUser] = useState(null);

    useEffect(() => {
        // Simple user detection
        const checkUser = () => {
            if (window.Clerk?.user) {
                setUser({
                    name: window.Clerk.user.fullName,
                    email: window.Clerk.user.primaryEmailAddress?.emailAddress,
                    image: window.Clerk.user.imageUrl
                });
            } else {
                // Fallback / Placeholder
                setUser({
                    name: 'Guest User',
                    email: 'guest@emailpilot.ai',
                    image: null
                });
            }
        };
        
        checkUser();
        // Listen for clerk events if possible, or just run once
    }, []);

    return (
        <div className="space-y-6 max-w-4xl mx-auto">
            {/* User Profile Header */}
            <div className="flex items-center gap-4 mb-8">
                <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center overflow-hidden border-2 border-background shadow-sm">
                    {user?.image ? (
                        <img src={user.image} alt={user.name} className="h-full w-full object-cover" />
                    ) : (
                        <Icon name="user" className="h-8 w-8 text-primary" />
                    )}
                </div>
                <div>
                    <h2 className="text-2xl font-bold">{user?.name}</h2>
                    <p className="text-muted-foreground">{user?.email}</p>
                </div>
            </div>

            {/* Integrations Section */}
            <div>
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                    <Icon name="grid" className="h-5 w-5" />
                    Integrations
                </h3>
                
                <div className="grid grid-cols-1 gap-6">
                    {/* Google Docs Integration (ReadOnly view) */}
                    <Card className="opacity-75">
                        <CardHeader>
                            <div className="flex items-start justify-between">
                                <div className="flex items-center gap-3">
                                    <div className="p-2 bg-blue-100 dark:bg-blue-900/20 rounded-lg text-blue-600 dark:text-blue-400">
                                        <Icon name="file-text" className="h-6 w-6" />
                                    </div>
                                    <div>
                                        <CardTitle className="text-lg">Google Docs Import</CardTitle>
                                        <CardDescription className="mt-1">
                                            Import documents directly from Google Drive
                                        </CardDescription>
                                    </div>
                                </div>
                                <Badge variant="success">Active</Badge>
                            </div>
                        </CardHeader>
                        <CardContent>
                            <p className="text-sm text-muted-foreground">
                                This integration is active. You can import documents via the "Upload" tab.
                            </p>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    );
}
