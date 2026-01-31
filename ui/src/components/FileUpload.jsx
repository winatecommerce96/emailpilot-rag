/**
 * Drag-and-Drop File Upload Component
 * Supports multiple files and images with preview
 */

import { Icon } from './ui.jsx';

const { useState, useCallback, useRef } = React;

// Allowed file types
const ALLOWED_TYPES = {
    // Documents
    'application/pdf': { icon: 'file-text', label: 'PDF' },
    'text/plain': { icon: 'file-text', label: 'TXT' },
    'text/markdown': { icon: 'file-text', label: 'MD' },
    'text/html': { icon: 'code', label: 'HTML' },
    'application/json': { icon: 'braces', label: 'JSON' },
    'text/csv': { icon: 'table', label: 'CSV' },
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': { icon: 'file-text', label: 'DOCX' },
    'application/msword': { icon: 'file-text', label: 'DOC' },
    // Images (coming soon)
    'image/png': { icon: 'image', label: 'PNG' },
    'image/jpeg': { icon: 'image', label: 'JPG' },
    'image/gif': { icon: 'image', label: 'GIF' },
    'image/webp': { icon: 'image', label: 'WEBP' },
};

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

export function FileUpload({
    onFilesSelected,
    onUpload,
    accept = '*/*',
    multiple = true,
    maxFiles = 10,
    disabled = false,
    uploading = false,
    progress = 0,
    className = '',
}) {
    const [isDragging, setIsDragging] = useState(false);
    const [files, setFiles] = useState([]);
    const [errors, setErrors] = useState([]);
    const fileInputRef = useRef(null);
    const dragCounterRef = useRef(0);

    const validateFile = useCallback((file) => {
        const errors = [];

        if (file.size > MAX_FILE_SIZE) {
            errors.push(`File exceeds 10MB limit`);
        }

        // Check for dangerous extensions
        const dangerousExts = ['.exe', '.bat', '.cmd', '.com', '.scr', '.vbs', '.js'];
        const ext = file.name.toLowerCase().slice(file.name.lastIndexOf('.'));
        if (dangerousExts.includes(ext)) {
            errors.push(`File type not allowed for security reasons`);
        }

        return errors;
    }, []);

    const processFiles = useCallback((fileList) => {
        const newFiles = [];
        const newErrors = [];

        Array.from(fileList).slice(0, maxFiles - files.length).forEach((file, index) => {
            const fileErrors = validateFile(file);

            if (fileErrors.length > 0) {
                newErrors.push({ name: file.name, errors: fileErrors });
            } else {
                // Create preview for images
                const isImage = file.type.startsWith('image/');
                const fileData = {
                    id: `${Date.now()}-${index}`,
                    file,
                    name: file.name,
                    size: file.size,
                    type: file.type,
                    isImage,
                    preview: isImage ? URL.createObjectURL(file) : null,
                    typeInfo: ALLOWED_TYPES[file.type] || { icon: 'file', label: 'FILE' },
                };
                newFiles.push(fileData);
            }
        });

        if (newFiles.length > 0) {
            const updatedFiles = [...files, ...newFiles];
            setFiles(updatedFiles);
            onFilesSelected?.(updatedFiles.map(f => f.file));
        }

        if (newErrors.length > 0) {
            setErrors(newErrors);
            setTimeout(() => setErrors([]), 5000);
        }
    }, [files, maxFiles, validateFile, onFilesSelected]);

    const handleDragEnter = useCallback((e) => {
        e.preventDefault();
        e.stopPropagation();
        dragCounterRef.current++;
        if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
            setIsDragging(true);
        }
    }, []);

    const handleDragLeave = useCallback((e) => {
        e.preventDefault();
        e.stopPropagation();
        dragCounterRef.current--;
        if (dragCounterRef.current === 0) {
            setIsDragging(false);
        }
    }, []);

    const handleDragOver = useCallback((e) => {
        e.preventDefault();
        e.stopPropagation();
    }, []);

    const handleDrop = useCallback((e) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragging(false);
        dragCounterRef.current = 0;

        if (disabled) return;

        const droppedFiles = e.dataTransfer.files;
        if (droppedFiles.length > 0) {
            processFiles(droppedFiles);
        }
    }, [disabled, processFiles]);

    const handleFileInput = useCallback((e) => {
        const selectedFiles = e.target.files;
        if (selectedFiles.length > 0) {
            processFiles(selectedFiles);
        }
        // Reset input
        e.target.value = '';
    }, [processFiles]);

    const removeFile = useCallback((id) => {
        setFiles(prev => {
            const updated = prev.filter(f => f.id !== id);
            // Revoke preview URL
            const removed = prev.find(f => f.id === id);
            if (removed?.preview) {
                URL.revokeObjectURL(removed.preview);
            }
            onFilesSelected?.(updated.map(f => f.file));
            return updated;
        });
    }, [onFilesSelected]);

    const clearAll = useCallback(() => {
        files.forEach(f => {
            if (f.preview) URL.revokeObjectURL(f.preview);
        });
        setFiles([]);
        onFilesSelected?.([]);
    }, [files, onFilesSelected]);

    const formatSize = (bytes) => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    const handleUpload = useCallback(() => {
        if (files.length > 0 && onUpload) {
            onUpload(files.map(f => f.file));
        }
    }, [files, onUpload]);

    return (
        <div className={`space-y-4 ${className}`}>
            {/* Drop Zone */}
            <div
                className={`drop-zone relative rounded-lg p-8 text-center transition-all ${
                    isDragging ? 'dragover' : ''
                } ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                onDragEnter={handleDragEnter}
                onDragLeave={handleDragLeave}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
                onClick={() => !disabled && fileInputRef.current?.click()}
            >
                <input
                    ref={fileInputRef}
                    type="file"
                    accept={accept}
                    multiple={multiple}
                    onChange={handleFileInput}
                    className="hidden"
                    disabled={disabled}
                />

                <div className="flex flex-col items-center gap-3">
                    <div className={`rounded-full p-4 ${isDragging ? 'bg-primary/10' : 'bg-muted'}`}>
                        <Icon name="upload-cloud" className={`h-8 w-8 ${isDragging ? 'text-primary' : 'text-muted-foreground'}`} />
                    </div>
                    <div>
                        <p className="text-sm font-medium">
                            {isDragging ? 'Drop files here' : 'Drag & drop files here'}
                        </p>
                        <p className="text-xs text-muted-foreground mt-1">
                            or click to browse (max {maxFiles} files, 10MB each)
                        </p>
                    </div>
                    <div className="flex flex-wrap gap-1 justify-center mt-2">
                        {['PDF', 'TXT', 'MD', 'DOCX', 'JSON', 'CSV'].map(type => (
                            <span key={type} className="text-xs px-2 py-0.5 bg-muted rounded-full text-muted-foreground">
                                {type}
                            </span>
                        ))}
                        <span className="text-xs px-2 py-0.5 bg-primary/10 text-primary rounded-full">
                            Images (coming soon)
                        </span>
                    </div>
                </div>
            </div>

            {/* Error Messages */}
            {errors.length > 0 && (
                <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3">
                    <div className="flex items-start gap-2">
                        <Icon name="alert-circle" className="h-4 w-4 text-destructive mt-0.5" />
                        <div className="text-sm">
                            {errors.map((err, i) => (
                                <p key={i} className="text-destructive">
                                    <span className="font-medium">{err.name}:</span> {err.errors.join(', ')}
                                </p>
                            ))}
                        </div>
                    </div>
                </div>
            )}

            {/* File List */}
            {files.length > 0 && (
                <div className="space-y-2">
                    <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">
                            {files.length} file{files.length > 1 ? 's' : ''} selected
                        </span>
                        <button
                            onClick={clearAll}
                            className="text-xs text-muted-foreground hover:text-foreground"
                            disabled={uploading}
                        >
                            Clear all
                        </button>
                    </div>

                    <div className="grid gap-2">
                        {files.map((file) => (
                            <div
                                key={file.id}
                                className="flex items-center gap-3 p-3 rounded-lg border bg-card"
                            >
                                {/* Preview or Icon */}
                                {file.isImage && file.preview ? (
                                    <img
                                        src={file.preview}
                                        alt={file.name}
                                        className="h-10 w-10 rounded object-cover"
                                    />
                                ) : (
                                    <div className="h-10 w-10 rounded bg-muted flex items-center justify-center">
                                        <Icon name={file.typeInfo.icon} className="h-5 w-5 text-muted-foreground" />
                                    </div>
                                )}

                                {/* File Info */}
                                <div className="flex-1 min-w-0">
                                    <p className="text-sm font-medium truncate">{file.name}</p>
                                    <p className="text-xs text-muted-foreground">
                                        {file.typeInfo.label} • {formatSize(file.size)}
                                    </p>
                                </div>

                                {/* Remove Button */}
                                {!uploading && (
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            removeFile(file.id);
                                        }}
                                        className="p-1 rounded hover:bg-muted"
                                    >
                                        <Icon name="x" className="h-4 w-4 text-muted-foreground" />
                                    </button>
                                )}
                            </div>
                        ))}
                    </div>

                    {/* Upload Progress */}
                    {uploading && (
                        <div className="space-y-2">
                            <div className="h-2 rounded-full bg-secondary overflow-hidden">
                                <div
                                    className="h-full bg-primary transition-all progress-bar"
                                    style={{ width: `${progress}%` }}
                                />
                            </div>
                            <p className="text-xs text-center text-muted-foreground">
                                Uploading... {progress}%
                            </p>
                        </div>
                    )}

                    {/* Upload Button */}
                    {!uploading && onUpload && (
                        <button
                            onClick={handleUpload}
                            disabled={files.length === 0}
                            className="w-full h-10 px-4 py-2 rounded-md bg-primary text-primary-foreground font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                            Upload {files.length} file{files.length > 1 ? 's' : ''}
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}

export default FileUpload;
