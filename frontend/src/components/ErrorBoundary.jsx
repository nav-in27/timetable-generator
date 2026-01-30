/**
 * Error Boundary Component
 * Catches React errors and shows a fallback UI instead of crashing
 */
import React from 'react';

class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null, errorInfo: null };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }

    componentDidCatch(error, errorInfo) {
        console.error('React Error Boundary caught:', error, errorInfo);
        this.setState({ errorInfo });
    }

    render() {
        if (this.state.hasError) {
            return (
                <div style={{
                    padding: '40px',
                    textAlign: 'center',
                    background: 'linear-gradient(135deg, #1e293b 0%, #334155 100%)',
                    minHeight: '100vh',
                    color: 'white'
                }}>
                    <h1 style={{ fontSize: '2rem', marginBottom: '20px' }}>⚠️ Something went wrong</h1>
                    <p style={{ marginBottom: '20px', opacity: 0.8 }}>
                        An error occurred in the application. Please try refreshing the page.
                    </p>
                    <button
                        onClick={() => window.location.reload()}
                        style={{
                            padding: '12px 24px',
                            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                            border: 'none',
                            borderRadius: '8px',
                            color: 'white',
                            fontSize: '16px',
                            cursor: 'pointer',
                            marginRight: '10px'
                        }}
                    >
                        🔄 Refresh Page
                    </button>
                    <button
                        onClick={() => this.setState({ hasError: false })}
                        style={{
                            padding: '12px 24px',
                            background: '#475569',
                            border: 'none',
                            borderRadius: '8px',
                            color: 'white',
                            fontSize: '16px',
                            cursor: 'pointer'
                        }}
                    >
                        Try Again
                    </button>
                    {this.state.error && (
                        <details style={{ marginTop: '30px', textAlign: 'left', maxWidth: '600px', margin: '30px auto' }}>
                            <summary style={{ cursor: 'pointer', marginBottom: '10px' }}>Error Details</summary>
                            <pre style={{
                                background: '#0f172a',
                                padding: '16px',
                                borderRadius: '8px',
                                overflow: 'auto',
                                fontSize: '12px'
                            }}>
                                {this.state.error.toString()}
                                {this.state.errorInfo?.componentStack}
                            </pre>
                        </details>
                    )}
                </div>
            );
        }

        return this.props.children;
    }
}

export default ErrorBoundary;
