/**
 * PDF Preview Modal Component
 * Displays PDF in an embedded viewer inside the application.
 * READ-ONLY display - no modifications to timetable data.
 */
import { useState, useEffect } from 'react';
import { X, Download, ZoomIn, ZoomOut, Loader } from 'lucide-react';
import './PDFPreviewModal.css';

export default function PDFPreviewModal({ isOpen, onClose, previewUrl, downloadUrl }) {
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [zoom, setZoom] = useState(100);

    useEffect(() => {
        if (isOpen) {
            setLoading(true);
            setError(null);
        }
    }, [isOpen]);

    const handleIframeLoad = () => {
        setLoading(false);
    };

    const handleIframeError = () => {
        setLoading(false);
        setError('Unable to load PDF preview. Please try downloading instead.');
    };

    const handleZoomIn = () => {
        setZoom(prev => Math.min(prev + 25, 200));
    };

    const handleZoomOut = () => {
        setZoom(prev => Math.max(prev - 25, 50));
    };

    const handleDownload = () => {
        window.open(downloadUrl, '_blank');
    };

    if (!isOpen) return null;

    return (
        <div className="pdf-modal-overlay" onClick={onClose}>
            <div className="pdf-modal" onClick={(e) => e.stopPropagation()}>
                <div className="pdf-modal-header">
                    <h3>Timetable Preview</h3>
                    <div className="pdf-modal-actions">
                        <button
                            className="btn btn-sm btn-secondary"
                            onClick={handleZoomOut}
                            disabled={zoom <= 50}
                        >
                            <ZoomOut size={16} />
                        </button>
                        <span className="zoom-level">{zoom}%</span>
                        <button
                            className="btn btn-sm btn-secondary"
                            onClick={handleZoomIn}
                            disabled={zoom >= 200}
                        >
                            <ZoomIn size={16} />
                        </button>
                        <button
                            className="btn btn-sm btn-primary"
                            onClick={handleDownload}
                        >
                            <Download size={16} />
                            Download
                        </button>
                        <button
                            className="btn btn-sm btn-secondary pdf-close-btn"
                            onClick={onClose}
                        >
                            <X size={16} />
                        </button>
                    </div>
                </div>
                <div className="pdf-modal-content">
                    {loading && (
                        <div className="pdf-loading">
                            <Loader size={24} className="spinning" />
                            <span>Loading preview...</span>
                        </div>
                    )}
                    {error ? (
                        <div className="pdf-error">
                            <p>{error}</p>
                            <button className="btn btn-primary" onClick={handleDownload}>
                                <Download size={16} />
                                Download PDF Instead
                            </button>
                        </div>
                    ) : (
                        <iframe
                            src={previewUrl}
                            className="pdf-viewer"
                            style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'top left' }}
                            onLoad={handleIframeLoad}
                            onError={handleIframeError}
                            title="Timetable PDF Preview"
                        />
                    )}
                </div>
            </div>
        </div>
    );
}
