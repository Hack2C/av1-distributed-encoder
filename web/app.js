// AV1 Transcoding Service - Frontend JavaScript

const socket = io();
let currentFilter = 'all';
let allFiles = [];
let currentProcessingFileId = null;  // Track currently processing file
let lastWebSocketProgress = null;  // Track last progress from WebSocket
let lastWebSocketUpdate = 0;  // Timestamp of last WebSocket update

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initializeEventListeners();
    loadStatus();
    loadFiles();
    
    // Refresh every 5 seconds
    setInterval(loadStatus, 5000);
});

// Event Listeners
function initializeEventListeners() {
    // Control buttons
    document.getElementById('btn-pause').addEventListener('click', pauseTranscoding);
    document.getElementById('btn-resume').addEventListener('click', resumeTranscoding);
    document.getElementById('btn-scan').addEventListener('click', rescanLibrary);
    
    // Bulk action buttons
    document.getElementById('btn-reset-failed').addEventListener('click', resetAllFailed);
    document.getElementById('btn-delete-completed').addEventListener('click', deleteCompleted);
    
    // Filter buttons
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            currentFilter = e.target.dataset.filter;
            updateBulkActions();
            renderFiles();
        });
    });
    
    // Socket.IO events
    socket.on('processing_started', handleProcessingStarted);
    socket.on('progress', handleProgress);
    socket.on('completed', handleCompleted);
    socket.on('error', handleError);
}

// API Calls
async function loadStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        if (data.success) {
            updateStatus(data.status, data.statistics);
        }
    } catch (error) {
        console.error('Failed to load status:', error);
    }
}

async function loadFiles() {
    try {
        const response = await fetch('/api/files');
        const data = await response.json();
        
        if (data.success) {
            allFiles = data.files;
            updateBulkActions();
            renderFiles();
        }
    } catch (error) {
        console.error('Failed to load files:', error);
    }
}

async function pauseTranscoding() {
    try {
        const response = await fetch('/api/pause', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            document.getElementById('btn-pause').disabled = true;
            document.getElementById('btn-resume').disabled = false;
            showNotification('Transcoding paused', 'warning');
        }
    } catch (error) {
        console.error('Failed to pause:', error);
        showNotification('Failed to pause', 'error');
    }
}

async function resumeTranscoding() {
    try {
        const response = await fetch('/api/resume', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            document.getElementById('btn-pause').disabled = false;
            document.getElementById('btn-resume').disabled = true;
            showNotification('Transcoding resumed', 'success');
        }
    } catch (error) {
        console.error('Failed to resume:', error);
        showNotification('Failed to resume', 'error');
    }
}

async function rescanLibrary() {
    const btn = document.getElementById('btn-scan');
    btn.disabled = true;
    btn.textContent = 'Scanning...';
    
    try {
        const response = await fetch('/api/scan', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            showNotification(data.message, 'success');
            loadFiles();
        } else {
            showNotification('Scan failed: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Failed to scan:', error);
        showNotification('Scan failed', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Rescan Library';
    }
}

// Update UI
function updateStatus(status, stats) {
    // Service status indicator
    const statusBadge = document.getElementById('service-status');
    statusBadge.className = 'status-badge';
    
    if (!status.running) {
        statusBadge.classList.add('stopped');
    } else if (status.paused) {
        statusBadge.classList.add('paused');
    } else {
        statusBadge.classList.add('running');
    }
    
    // Statistics
    document.getElementById('total-files').textContent = stats.total_files || 0;
    document.getElementById('completed-files').textContent = stats.completed_files || 0;
    document.getElementById('pending-files').textContent = stats.pending_files || 0;
    document.getElementById('failed-files').textContent = stats.failed_files || 0;
    
    // Disk space
    const originalGB = (stats.total_original_size / 1e9).toFixed(2);
    const transcodedGB = (stats.total_transcoded_size / 1e9).toFixed(2);
    const savedGB = (stats.total_savings_bytes / 1e9).toFixed(2);
    const estimatedSavingsGB = (stats.estimated_total_savings / 1e9).toFixed(2);
    const estimatedFinalGB = (stats.estimated_final_size / 1e9).toFixed(2);
    const savingsPercent = stats.total_savings_percent || 0;
    
    document.getElementById('original-size').textContent = `${originalGB} GB`;
    document.getElementById('current-size').textContent = `${transcodedGB} GB`;
    document.getElementById('saved-size').textContent = `${savedGB} GB (${savingsPercent.toFixed(1)}%)`;
    document.getElementById('estimated-savings').textContent = `${estimatedSavingsGB} GB (${savingsPercent.toFixed(1)}%)`;
    document.getElementById('estimated-final-size').textContent = `${estimatedFinalGB} GB`;
    
    // Overall progress
    const progressPercent = stats.total_files > 0 
        ? (stats.completed_files / stats.total_files * 100) 
        : 0;
    document.getElementById('overall-progress').style.width = `${progressPercent}%`;
    
    // Current file
    if (status.current_file) {
        document.getElementById('current-file-section').style.display = 'block';
        const file = status.current_file;
        
        // Track currently processing file ID
        currentProcessingFileId = file.id;
        
        document.getElementById('current-file-name').textContent = file.filename || '-';
        document.getElementById('current-file-directory').textContent = file.directory || '-';
        document.getElementById('current-file-codec').textContent = file.source_codec || '-';
        document.getElementById('current-file-resolution').textContent = file.source_resolution || '-';
        document.getElementById('current-file-crf').textContent = file.target_crf || '-';
        
        // Use WebSocket progress if we got an update in the last 10 seconds
        // Otherwise fall back to API progress
        const useWebSocketProgress = (Date.now() - lastWebSocketUpdate) < 10000;
        const fileProgress = useWebSocketProgress ? 
            (lastWebSocketProgress !== null ? lastWebSocketProgress : file.progress_percent || 0) :
            (file.progress_percent || 0);
        
        document.getElementById('current-file-progress').style.width = `${fileProgress}%`;
        document.getElementById('current-file-percent').textContent = `${fileProgress.toFixed(1)}%`;
    } else {
        document.getElementById('current-file-section').style.display = 'none';
        // Reset WebSocket progress when no file is processing
        currentProcessingFileId = null;
        lastWebSocketProgress = null;
        lastWebSocketUpdate = 0;
    }
    
    // Last update time
    document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
}

function renderFiles() {
    const tbody = document.getElementById('files-tbody');
    
    // Filter files
    let filteredFiles = allFiles;
    if (currentFilter !== 'all') {
        filteredFiles = allFiles.filter(f => f.status === currentFilter);
    }
    
    // Sort by created_at DESC
    filteredFiles.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    
    // Render
    if (filteredFiles.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="loading">No files found</td></tr>';
        return;
    }
    
    tbody.innerHTML = filteredFiles.map(file => {
        const originalMB = (file.size_bytes / 1e6).toFixed(1);
        const newMB = file.output_size_bytes ? (file.output_size_bytes / 1e6).toFixed(1) : '-';
        const savingsPercent = file.savings_percent ? file.savings_percent.toFixed(1) : '-';
        const savingsMB = file.savings_bytes ? (file.savings_bytes / 1e6).toFixed(1) : '-';
        
        // Shorten directory path for display
        const dirParts = (file.directory || '').split('/');
        const shortDir = dirParts.length > 2 
            ? '.../' + dirParts.slice(-2).join('/')
            : file.directory || '-';
        
        // Action buttons based on status
        let actions = '';
        if (file.status === 'failed') {
            actions = `
                <button class="action-btn action-btn-reset" onclick="resetFile(${file.id})">🔄 Reset</button>
                <button class="action-btn action-btn-skip" onclick="skipFile(${file.id})">⏭️ Skip</button>
            `;
        } else if (file.status === 'processing') {
            // Show abort for currently processing file, retry for stuck files
            if (file.id === currentProcessingFileId) {
                actions = `<button class="action-btn action-btn-delete" onclick="abortFile()" title="Abort current transcoding">⏹️ Abort</button>`;
            } else {
                actions = `<button class="action-btn action-btn-reset" onclick="retryFile(${file.id})" title="Stuck? Click to retry">🔄 Retry</button>`;
            }
        } else if (file.status === 'pending') {
            actions = `<button class="action-btn action-btn-skip" onclick="skipFile(${file.id})">⏭️ Skip</button>`;
        } else if (file.status === 'completed') {
            actions = `<button class="action-btn action-btn-delete" onclick="deleteFile(${file.id})">🗑️ Delete</button>`;
        } else {
            actions = '-';
        }
        
        return `
            <tr>
                <td>
                    <span class="status-icon status-${file.status}"></span>
                    ${file.status}
                </td>
                <td title="${file.path}">${file.filename}</td>
                <td title="${file.directory}">${shortDir}</td>
                <td>${file.source_resolution || '-'}</td>
                <td>${file.source_codec || '-'}</td>
                <td>${originalMB} MB</td>
                <td>${newMB} MB</td>
                <td>${savingsMB} MB (${savingsPercent}%)</td>
                <td>${actions}</td>
            </tr>
        `;
    }).join('');
}

// Socket.IO Handlers
function handleProcessingStarted(data) {
    console.log('Processing started:', data);
    loadStatus();
}

function handleProgress(data) {
    // Update progress bar for current file
    if (data.file_id) {
        const progress = data.percent || 0;
        
        // Store the latest WebSocket progress
        lastWebSocketProgress = progress;
        lastWebSocketUpdate = Date.now();
        
        // Update UI immediately
        document.getElementById('current-file-progress').style.width = `${progress}%`;
        document.getElementById('current-file-percent').textContent = `${progress.toFixed(1)}%`;
    }
}

function handleCompleted(data) {
    console.log('File completed:', data);
    showNotification(`Completed: ${data.file}`, 'success');
    loadStatus();
    loadFiles();
}

function handleError(data) {
    console.error('Error:', data);
    showNotification(`Error: ${data.error || 'Unknown error'}`, 'error');
    loadStatus();
}

// Notifications
function showNotification(message, type = 'info') {
    // Simple console notification for now
    // You can implement a toast notification system here
    console.log(`[${type.toUpperCase()}] ${message}`);
    
    // Optional: Create a simple alert
    const colors = {
        success: '#10b981',
        warning: '#f59e0b',
        error: '#ef4444',
        info: '#2563eb'
    };
    
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${colors[type] || colors.info};
        color: white;
        padding: 16px 24px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        z-index: 10000;
        font-weight: 600;
        max-width: 400px;
    `;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.transition = 'opacity 0.3s';
        notification.style.opacity = '0';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Utility Functions
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatDuration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hours > 0) {
        return `${hours}h ${minutes}m`;
    } else if (minutes > 0) {
        return `${minutes}m ${secs}s`;
    } else {
        return `${secs}s`;
    }
}

// Bulk Actions
function updateBulkActions() {
    const bulkActions = document.getElementById('bulk-actions');
    const failedCount = allFiles.filter(f => f.status === 'failed').length;
    const completedCount = allFiles.filter(f => f.status === 'completed').length;
    
    // Show bulk actions if there are failed or completed files
    if (failedCount > 0 || completedCount > 0) {
        bulkActions.style.display = 'flex';
    } else {
        bulkActions.style.display = 'none';
    }
    
    // Update button text with counts
    const resetBtn = document.getElementById('btn-reset-failed');
    const deleteBtn = document.getElementById('btn-delete-completed');
    
    resetBtn.textContent = `🔄 Reset All Failed to Pending (${failedCount})`;
    resetBtn.disabled = failedCount === 0;
    
    deleteBtn.textContent = `🗑️ Remove Completed (${completedCount})`;
    deleteBtn.disabled = completedCount === 0;
}

async function resetAllFailed() {
    const failedFiles = allFiles.filter(f => f.status === 'failed');
    
    if (failedFiles.length === 0) {
        showNotification('No failed files to reset', 'info');
        return;
    }
    
    if (!confirm(`Reset ${failedFiles.length} failed file(s) to pending?`)) {
        return;
    }
    
    try {
        const response = await fetch('/api/files/reset-failed', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            showNotification(`Reset ${data.count} file(s) to pending`, 'success');
            loadFiles();
            loadStatus();
        } else {
            showNotification(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showNotification(`Error: ${error.message}`, 'error');
    }
}

async function deleteCompleted() {
    const completedFiles = allFiles.filter(f => f.status === 'completed');
    
    if (completedFiles.length === 0) {
        showNotification('No completed files to remove', 'info');
        return;
    }
    
    if (!confirm(`Remove ${completedFiles.length} completed file(s) from the database?\n\nThis will NOT delete the actual files, only the database records.`)) {
        return;
    }
    
    try {
        const response = await fetch('/api/files/delete-completed', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            showNotification(`Removed ${data.count} file(s) from database`, 'success');
            loadFiles();
            loadStatus();
        } else {
            showNotification(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showNotification(`Error: ${error.message}`, 'error');
    }
}

// Individual File Actions
async function resetFile(fileId) {
    try {
        const response = await fetch(`/api/files/${fileId}/reset`, { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            showNotification('File reset to pending', 'success');
            loadFiles();
            loadStatus();
        } else {
            showNotification(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showNotification(`Error: ${error.message}`, 'error');
    }
}

async function skipFile(fileId) {
    if (!confirm('Skip this file? It will be marked as completed without processing.')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/files/${fileId}/skip`, { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            showNotification('File skipped', 'success');
            loadFiles();
            loadStatus();
        } else {
            showNotification(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showNotification(`Error: ${error.message}`, 'error');
    }
}

async function retryFile(fileId) {
    if (!confirm('Retry this file? It will be reset to pending and requeued.')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/files/${fileId}/retry`, { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            showNotification('File will be retried', 'success');
            loadFiles();
            loadStatus();
        } else {
            showNotification(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showNotification(`Error: ${error.message}`, 'error');
    }
}

async function abortFile() {
    if (!confirm('Abort the current transcoding?\n\nThe file will be marked as failed and you can retry it later.')) {
        return;
    }
    
    try {
        const response = await fetch('/api/abort', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            showNotification('Transcoding aborted', 'warning');
            loadFiles();
            loadStatus();
        } else {
            showNotification(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showNotification(`Error: ${error.message}`, 'error');
    }
}

async function deleteFile(fileId) {
    if (!confirm('Remove this file from the database?\n\nThis will NOT delete the actual file, only the database record.')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/files/${fileId}/delete`, { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            showNotification('File removed from database', 'success');
            loadFiles();
            loadStatus();
        } else {
            showNotification(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showNotification(`Error: ${error.message}`, 'error');
    }
}

