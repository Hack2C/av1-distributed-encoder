// Master Server Dashboard - Modern UI
const socket = io();

// State
let filesData = [];
let workersData = {};
let statistics = {};
let currentFilter = 'all';
let currentSearch = '';

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initializeEventListeners();
    fetchInitialData();
    connectWebSocket();
});

// Event Listeners
function initializeEventListeners() {
    document.getElementById('scanBtn').addEventListener('click', triggerScan);
    document.getElementById('refreshBtn').addEventListener('click', fetchInitialData);
    document.getElementById('statusFilter').addEventListener('change', (e) => {
        currentFilter = e.target.value;
        filterAndRenderFiles();
    });
    document.getElementById('searchInput').addEventListener('input', (e) => {
        currentSearch = e.target.value.toLowerCase();
        filterAndRenderFiles();
    });
}

// API Calls
async function fetchInitialData() {
    try {
        const [statusRes, filesRes] = await Promise.all([
            fetch('/api/status'),
            fetch('/api/files')
        ]);
        
        const statusData = await statusRes.json();
        const filesResData = await filesRes.json();
        
        if (statusData.success) {
            statistics = statusData.statistics;
            workersData = statusData.workers;
            updateDashboard();
            updateWorkers();
        }
        
        if (filesResData.success) {
            filesData = filesResData.files;
            filterAndRenderFiles();
        }
    } catch (error) {
        console.error('Error fetching data:', error);
    }
}

async function triggerScan() {
    const btn = document.getElementById('scanBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="icon">⏳</span> Scanning...';
    
    try {
        const response = await fetch('/api/scan', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            showNotification('Scan completed successfully', 'success');
            await fetchInitialData();
        } else {
            showNotification('Scan failed: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('Error: ' + error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="icon">🔍</span> Scan Library';
    }
}

async function controlFile(fileId, action) {
    try {
        const response = await fetch(`/api/file/${fileId}/${action}`, { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            showNotification(data.message, 'success');
            await fetchInitialData();
        } else {
            showNotification('Error: ' + data.error, 'error');
        }
    } catch (error) {
        showNotification('Error: ' + error.message, 'error');
    }
}

// WebSocket
function connectWebSocket() {
    socket.on('connect', () => {
        console.log('WebSocket connected');
    });
    
    socket.on('status_update', (data) => {
        statistics = data.statistics;
        workersData = data.workers;
        updateDashboard();
        updateWorkers();
    });
    
    socket.on('progress', (data) => {
        updateFileProgress(data);
    });
    
    socket.on('disconnect', () => {
        console.log('WebSocket disconnected');
    });
}

// Update Dashboard
function updateDashboard() {
    document.getElementById('totalFiles').textContent = statistics.total_files || 0;
    document.getElementById('pendingFiles').textContent = statistics.pending_files || 0;
    document.getElementById('processingFiles').textContent = statistics.processing_files || 0;
    document.getElementById('completedFiles').textContent = statistics.completed_files || 0;
    
    const savingsGB = ((statistics.total_savings_bytes || 0) / (1024 * 1024 * 1024)).toFixed(2);
    document.getElementById('totalSavings').textContent = savingsGB + ' GB';
    
    // Calculate estimated time
    const estimatedTime = calculateEstimatedTime();
    document.getElementById('estimatedTime').textContent = estimatedTime;
}

function calculateEstimatedTime() {
    const processing = statistics.processing_files || 0;
    const pending = statistics.pending_files || 0;
    
    if (processing === 0) {
        return '--:--';
    }
    
    // Calculate average speed from active workers
    let totalSpeed = 0;
    let activeWorkers = 0;
    
    Object.values(workersData).forEach(worker => {
        if (worker.status === 'processing' && worker.current_speed) {
            totalSpeed += worker.current_speed;
            activeWorkers++;
        }
    });
    
    if (activeWorkers === 0 || totalSpeed === 0) {
        return '--:--';
    }
    
    // Rough estimate: assume average file is 30 minutes at 30fps = 54000 frames
    const avgFramesPerFile = 54000;
    const remainingFiles = processing + pending;
    const estimatedSeconds = (remainingFiles * avgFramesPerFile) / (totalSpeed / activeWorkers);
    
    return formatDuration(estimatedSeconds);
}

function formatDuration(seconds) {
    if (!seconds || seconds < 0) return '--:--';
    
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    
    if (hours > 24) {
        const days = Math.floor(hours / 24);
        return `${days}d ${hours % 24}h`;
    } else if (hours > 0) {
        return `${hours}h ${minutes}m`;
    } else {
        return `${minutes}m`;
    }
}

// Update Workers
function updateWorkers() {
    const grid = document.getElementById('workersGrid');
    
    const workers = Object.entries(workersData);
    
    if (workers.length === 0) {
        grid.innerHTML = '<div class="empty-state">No workers connected</div>';
        return;
    }
    
    grid.innerHTML = workers.map(([workerId, worker]) => {
        const statusClass = worker.status || 'offline';
        const cpuUsage = (worker.cpu_percent || 0).toFixed(1);
        const memUsage = (worker.memory_percent || 0).toFixed(1);
        const progress = worker.current_progress || 0;
        
        let currentFileInfo = '';
        if (worker.status === 'processing' && worker.current_file) {
            const eta = worker.current_eta ? formatDuration(worker.current_eta) : '--:--';
            const speed = worker.current_speed ? `${worker.current_speed.toFixed(1)} fps` : '--';
            
            currentFileInfo = `
                <div class="worker-current-file">
                    <div class="worker-current-file-label">Processing:</div>
                    <div class="worker-current-file-name">${escapeHtml(worker.current_file)}</div>
                    <div class="worker-progress">
                        <div class="progress-bar-container">
                            <div class="progress-bar" style="width: ${progress}%"></div>
                        </div>
                        <div class="progress-text">
                            <span>${progress.toFixed(1)}%</span>
                            <span>${speed} | ETA: ${eta}</span>
                        </div>
                    </div>
                </div>
            `;
        }
        
        const fadeOutClass = worker.fade_out ? 'faded-out' : '';
        const fadeOutIndicator = worker.fade_out ? '<span class="fade-out-indicator">⏸️ FADING OUT</span>' : '';
        const fadeOutButton = `<button class="btn btn-small ${worker.fade_out ? 'btn-success' : 'btn-warning'}" 
                                      onclick="toggleWorkerFadeOut('${worker.id || workerId}', '${escapeHtml(worker.display_name || workerId)}')"
                                      title="${worker.fade_out ? 'Enable worker for new jobs' : 'Prevent worker from taking new jobs'}">
                                  ${worker.fade_out ? '▶️ Enable' : '⏸️ Fade Out'}
                              </button>`;
        
        return `
            <div class="worker-card ${statusClass} ${fadeOutClass}">
                <div class="worker-header">
                    <div class="worker-name-container">
                        <div class="worker-name" title="Full ID: ${escapeHtml(worker.id || workerId)}">${escapeHtml(worker.display_name || workerId)}</div>
                        ${fadeOutIndicator}
                    </div>
                    <div class="worker-controls">
                        <div class="worker-status ${statusClass}">${statusClass}</div>
                        ${fadeOutButton}
                    </div>
                </div>
                <div class="worker-info">
                    <div class="worker-stat">
                        <div class="worker-stat-label">Hostname</div>
                        <div class="worker-stat-value">${escapeHtml(worker.hostname || 'Unknown')}</div>
                    </div>
                    <div class="worker-stat">
                        <div class="worker-stat-label">Version</div>
                        <div class="worker-stat-value">${escapeHtml(worker.version || 'N/A')}</div>
                    </div>
                    <div class="worker-stat">
                        <div class="worker-stat-label">CPU Cores</div>
                        <div class="worker-stat-value">${worker.capabilities?.cpu_count || 'N/A'}</div>
                    </div>
                    <div class="worker-stat">
                        <div class="worker-stat-label">Total RAM</div>
                        <div class="worker-stat-value">${worker.capabilities?.memory_total ? (worker.capabilities.memory_total / (1024*1024*1024)).toFixed(1) + ' GB' : 'N/A'}</div>
                    </div>
                    <div class="worker-stat">
                        <div class="worker-stat-label">CPU Usage</div>
                        <div class="worker-stat-value">${cpuUsage}%</div>
                    </div>
                    <div class="worker-stat">
                        <div class="worker-stat-label">Memory</div>
                        <div class="worker-stat-value">${memUsage}%</div>
                    </div>
                </div>
                ${currentFileInfo}
            </div>
        `;
    }).join('');
}

// Update Files
function filterAndRenderFiles() {
    let filtered = filesData;
    
    // Apply status filter
    if (currentFilter !== 'all') {
        filtered = filtered.filter(file => file.status === currentFilter);
    }
    
    // Apply search
    if (currentSearch) {
        filtered = filtered.filter(file => 
            file.filename.toLowerCase().includes(currentSearch) ||
            file.path.toLowerCase().includes(currentSearch)
        );
    }
    
    renderFiles(filtered);
}

function renderFiles(files) {
    const list = document.getElementById('fileList');
    
    if (files.length === 0) {
        list.innerHTML = '<div class="empty-state">No files found</div>';
        return;
    }
    
    list.innerHTML = files.map(file => {
        const sizeGB = ((file.size_bytes || 0) / (1024 * 1024 * 1024)).toFixed(2);
        const savingsGB = file.savings_bytes ? ((file.savings_bytes) / (1024 * 1024 * 1024)).toFixed(2) : '--';
        const savingsPercent = file.savings_percent ? file.savings_percent.toFixed(1) : '--';
        
        let progressBar = '';
        if (file.status === 'processing') {
            const progress = file.progress_percent || 0;
            const speed = file.processing_speed_fps ? `${file.processing_speed_fps.toFixed(1)} fps` : '--';
            const eta = file.time_remaining_seconds ? formatDuration(file.time_remaining_seconds) : '--:--';
            const statusMsg = file.status_message || 'Processing...';
            
            progressBar = `
                <div class="file-progress">
                    <div class="file-progress-info">
                        <span>${progress.toFixed(1)}%</span>
                        <span>${speed} | ETA: ${eta}</span>
                    </div>
                    <div class="file-progress-status">
                        <small>${escapeHtml(statusMsg)}</small>
                    </div>
                    <div class="progress-bar-container">
                        <div class="progress-bar" style="width: ${progress}%"></div>
                    </div>
                </div>
            `;
        }
        
        let actions = '';
        if (file.status === 'pending') {
            actions = `
                <button class="btn btn-small btn-primary" onclick="showPriorityModal(${file.id})">🚀 Push to Top</button>
                <button class="btn btn-small btn-warning" onclick="controlFile(${file.id}, 'skip')">Skip</button>
                <button class="btn btn-small btn-danger" onclick="controlFile(${file.id}, 'delete')">Delete</button>
            `;
        } else if (file.status === 'processing') {
            actions = `
                <button class="btn btn-small btn-danger" onclick="controlFile(${file.id}, 'cancel')">Cancel</button>
            `;
        } else if (file.status === 'failed') {
            actions = `
                <button class="btn btn-small btn-primary" onclick="showPriorityModal(${file.id})">🚀 Push to Top</button>
                <button class="btn btn-small btn-success" onclick="controlFile(${file.id}, 'retry')">Retry</button>
                <button class="btn btn-small btn-danger" onclick="controlFile(${file.id}, 'delete')">Delete</button>
            `;
        } else if (file.status === 'completed') {
            actions = `
                <button class="btn btn-small btn-secondary" onclick="controlFile(${file.id}, 'retry')">Re-encode</button>
            `;
        }
        
        const details = `
            <div class="file-details">
                <div class="file-detail">
                    <div class="file-detail-label">Resolution</div>
                    <div class="file-detail-value">${escapeHtml(file.source_resolution || 'Unknown')}</div>
                </div>
                <div class="file-detail">
                    <div class="file-detail-label">Source Codec</div>
                    <div class="file-detail-value">${escapeHtml(file.source_codec || 'Unknown')}</div>
                </div>
                <div class="file-detail">
                    <div class="file-detail-label">Audio</div>
                    <div class="file-detail-value">${escapeHtml(file.source_audio_codec || 'Unknown')}</div>
                </div>
                <div class="file-detail">
                    <div class="file-detail-label">Original Size</div>
                    <div class="file-detail-value">${sizeGB} GB</div>
                </div>
                ${file.status === 'completed' ? `
                    <div class="file-detail">
                        <div class="file-detail-label">Space Saved</div>
                        <div class="file-detail-value">${savingsGB} GB (${savingsPercent}%)</div>
                    </div>
                ` : ''}
                ${file.assigned_worker_id ? `
                    <div class="file-detail">
                        <div class="file-detail-label">Worker</div>
                        <div class="file-detail-value">${escapeHtml(file.assigned_worker_id)}</div>
                    </div>
                ` : ''}
                ${file.target_crf ? `
                    <div class="file-detail">
                        <div class="file-detail-label">Target CRF</div>
                        <div class="file-detail-value">${file.target_crf}</div>
                    </div>
                ` : ''}
            </div>
        `;
        
        return `
            <div class="file-item ${file.status}">
                <div class="file-item-header">
                    <div class="file-item-info">
                        <div class="file-item-name">${escapeHtml(file.filename)}</div>
                        <div class="file-item-meta">
                            <span>📁 ${escapeHtml(file.directory)}</span>
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        ${(file.priority > 0) ? '<div class="priority-badge">🚀 HIGH PRIORITY</div>' : ''}
                        ${file.preferred_worker_display_name ? `<div class="worker-assigned-badge">👤 ${file.preferred_worker_display_name}</div>` : ''}
                        <div class="file-status-badge ${file.status}">${file.status}</div>
                        <div class="file-item-actions">
                            ${actions}
                        </div>
                    </div>
                </div>
                ${progressBar}
                ${details}
                ${file.error_message ? `<div style="color: var(--accent-red); margin-top: 10px; font-size: 0.9em;">❌ ${escapeHtml(file.error_message)}</div>` : ''}
            </div>
        `;
    }).join('');
}

function updateFileProgress(data) {
    const fileIndex = filesData.findIndex(f => f.id === data.file_id);
    if (fileIndex !== -1) {
        filesData[fileIndex].progress_percent = data.percent;
        filesData[fileIndex].processing_speed_fps = data.speed;
        filesData[fileIndex].time_remaining_seconds = data.eta;
        filesData[fileIndex].status_message = data.status; // Add status message
        filterAndRenderFiles();
    }
}

// Utilities
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showNotification(message, type = 'info') {
    // Simple notification (can be enhanced with a notification library)
    console.log(`[${type.toUpperCase()}] ${message}`);
    alert(message);
}

// Priority Modal Functions
let selectedFileId = null;
let selectedWorkerId = null;

async function showPriorityModal(fileId) {
    selectedFileId = fileId;
    selectedWorkerId = null;
    
    const modal = document.getElementById('priorityModal');
    const workerSelection = document.getElementById('workerSelection');
    const confirmBtn = document.getElementById('confirmBtn');
    
    // Show modal
    modal.style.display = 'block';
    
    // Reset state
    workerSelection.innerHTML = '<div class="worker-option loading">Loading workers...</div>';
    confirmBtn.disabled = true;
    
    try {
        // Fetch current workers
        const response = await fetch('/api/workers');
        const data = await response.json();
        
        if (data.success && data.workers && data.workers.length > 0) {
            // Render worker options
            workerSelection.innerHTML = data.workers.map(worker => `
                <div class="worker-option" onclick="selectWorker('${worker.id}')">
                    <div class="worker-info">
                        <div class="worker-name">${worker.id}</div>
                        <div class="worker-stats">
                            ${worker.capabilities.cpu_count} cores • 
                            ${(worker.capabilities.memory_total / 1024 / 1024 / 1024).toFixed(1)} GB RAM
                        </div>
                    </div>
                    <div class="worker-status ${worker.status}">
                        ${worker.status}
                    </div>
                </div>
            `).join('');
        } else {
            workerSelection.innerHTML = '<div class="worker-option">No workers available</div>';
        }
    } catch (error) {
        console.error('Error fetching workers:', error);
        workerSelection.innerHTML = '<div class="worker-option">Error loading workers</div>';
    }
}

function selectWorker(workerId) {
    console.log('selectWorker called with:', workerId);
    selectedWorkerId = workerId;
    
    // Update UI
    document.querySelectorAll('.worker-option').forEach(option => {
        option.classList.remove('selected');
    });
    
    event.target.closest('.worker-option').classList.add('selected');
    
    // Enable confirm button
    document.getElementById('confirmBtn').disabled = false;
    console.log('Worker selected:', selectedWorkerId);
}

function closePriorityModal() {
    document.getElementById('priorityModal').style.display = 'none';
    selectedFileId = null;
    selectedWorkerId = null;
}

async function confirmPriority() {
    console.log('confirmPriority called', { selectedFileId, selectedWorkerId });
    
    if (!selectedFileId || !selectedWorkerId) {
        console.log('Missing fileId or workerId');
        showNotification('Please select a worker', 'error');
        return;
    }
    
    console.log('Making API call...');
    try {
        const response = await fetch(`/api/file/${selectedFileId}/priority`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                preferred_worker_id: selectedWorkerId
            })
        });
        
        console.log('Response status:', response.status);
        const result = await response.json();
        console.log('API response:', result);
        
        if (result.success) {
            showNotification(`File pushed to top of queue${result.preferred_worker_id ? ` for ${result.preferred_worker_id}` : ''}!`, 'success');
            
            // Update the file in our local data if returned
            if (result.file) {
                const fileIndex = filesData.findIndex(f => f.id === selectedFileId);
                if (fileIndex !== -1) {
                    filesData[fileIndex] = result.file;
                    filterAndRenderFiles();
                }
            }
            
            closePriorityModal();
            // Also refresh to get latest data
            fetchInitialData();
        } else {
            showNotification(result.error || 'Failed to prioritize file', 'error');
        }
    } catch (error) {
        console.error('Error setting priority:', error);
        showNotification('Failed to prioritize file', 'error');
    }
}

// Worker Fade Out Control
async function toggleWorkerFadeOut(workerId, displayName) {
    try {
        const response = await fetch(`/api/worker/${workerId}/fade_out`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (result.success) {
            const action = result.fade_out ? 'faded out' : 'enabled';
            showNotification(`Worker ${displayName} ${action}`, 'success');
            
            // Refresh worker data
            fetchInitialData();
        } else {
            showNotification(result.error || 'Failed to toggle worker fade out', 'error');
        }
    } catch (error) {
        console.error('Error toggling worker fade out:', error);
        showNotification('Failed to toggle worker fade out', 'error');
    }
}

// Close modal when clicking outside
window.onclick = function(event) {
    const modal = document.getElementById('priorityModal');
    if (event.target === modal) {
        closePriorityModal();
    }
}

// Export for onclick handlers
window.controlFile = controlFile;
