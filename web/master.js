// Master UI JavaScript

const socket = io();
let workers = {};
let files = {};
let stats = {};

// Connect to WebSocket
socket.on('connect', () => {
    console.log('Connected to master server');
    loadInitialData();
});

socket.on('disconnect', () => {
    console.log('Disconnected from master server');
});

// Listen for real-time updates
socket.on('worker_registered', (data) => {
    console.log('Worker registered:', data.worker_id);
    loadInitialData();
});

socket.on('worker_offline', (data) => {
    console.log('Worker offline:', data.worker_id);
    if (workers[data.worker_id]) {
        workers[data.worker_id].status = 'offline';
        updateWorkersDisplay();
    }
});

socket.on('progress', (data) => {
    if (files[data.file_id]) {
        files[data.file_id].progress_percent = data.percent;
        files[data.file_id].worker_id = data.worker_id;
        updateQueueDisplay();
    }
});

socket.on('completed', (data) => {
    console.log('Job completed:', data.file_id);
    loadInitialData();
});

socket.on('error', (data) => {
    console.error('Job error:', data.file_id, data.message);
    loadInitialData();
});

socket.on('status_update', (data) => {
    workers = data.workers || {};
    updateWorkersDisplay();
    updateSummary();
});

// Load initial data
async function loadInitialData() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        
        if (data.success) {
            workers = data.workers || {};
            files = {};
            
            // Convert files array to object keyed by ID
            if (data.files) {
                data.files.forEach(file => {
                    files[file.id] = file;
                });
            }
            
            stats = data.statistics || {};
            
            updateWorkersDisplay();
            updateQueueDisplay();
            updateSummary();
        }
    } catch (error) {
        console.error('Error loading data:', error);
    }
}

// Update workers display
function updateWorkersDisplay() {
    const container = document.getElementById('workers-container');
    
    if (!workers || Object.keys(workers).length === 0) {
        container.innerHTML = '<p style="color: #95a5a6; text-align: center; padding: 40px;">No workers connected</p>';
        return;
    }
    
    container.innerHTML = '';
    
    Object.entries(workers).forEach(([workerId, worker]) => {
        const card = document.createElement('div');
        card.className = `worker-card ${worker.status}`;
        
        const statusClass = worker.status || 'offline';
        const cpuPercent = worker.cpu_percent || 0;
        const memPercent = worker.memory_percent || 0;
        const jobsCompleted = worker.jobs_completed || 0;
        const jobsFailed = worker.jobs_failed || 0;
        const currentProgress = worker.current_progress || 0;
        
        let progressHtml = '';
        if (worker.status === 'processing' && currentProgress > 0) {
            progressHtml = `
                <div class="worker-progress">
                    <div class="worker-current-job">Processing job...</div>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${currentProgress}%"></div>
                        <div class="progress-text">${currentProgress.toFixed(1)}%</div>
                    </div>
                </div>
            `;
        }
        
        card.innerHTML = `
            <div class="worker-header">
                <div class="worker-name">${worker.hostname || workerId}</div>
                <div class="worker-status ${statusClass}">${statusClass}</div>
            </div>
            <div class="worker-info">
                <div class="worker-stat">
                    <div class="worker-stat-label">CPU Usage</div>
                    <div class="worker-stat-value">${cpuPercent.toFixed(1)}%</div>
                </div>
                <div class="worker-stat">
                    <div class="worker-stat-label">Memory</div>
                    <div class="worker-stat-value">${memPercent.toFixed(1)}%</div>
                </div>
                <div class="worker-stat">
                    <div class="worker-stat-label">Completed</div>
                    <div class="worker-stat-value">${jobsCompleted}</div>
                </div>
                <div class="worker-stat">
                    <div class="worker-stat-label">Failed</div>
                    <div class="worker-stat-value">${jobsFailed}</div>
                </div>
            </div>
            ${progressHtml}
        `;
        
        container.appendChild(card);
    });
}

// Update queue display
function updateQueueDisplay() {
    const tbody = document.getElementById('queue-body');
    
    const filesList = Object.values(files);
    
    if (filesList.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: #95a5a6;">No files in queue</td></tr>';
        return;
    }
    
    tbody.innerHTML = '';
    
    filesList.forEach(file => {
        const tr = document.createElement('tr');
        tr.className = `status-${file.status}`;
        
        const size = formatFileSize(file.size_bytes);
        const resolution = file.source_resolution || 'Unknown';
        const status = file.status || 'pending';
        const progress = file.progress_percent || 0;
        
        let workerName = '-';
        if (file.worker_id && workers[file.worker_id]) {
            workerName = workers[file.worker_id].hostname || file.worker_id;
        }
        
        let savingsHtml = '-';
        if (file.savings_percent != null) {
            const savingsClass = file.savings_percent > 0 ? 'positive' : 'negative';
            savingsHtml = `<span class="${savingsClass}">${file.savings_percent.toFixed(1)}%</span>`;
        }
        
        let progressHtml = '-';
        if (status === 'processing') {
            progressHtml = `
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${progress}%"></div>
                    <div class="progress-text">${progress.toFixed(1)}%</div>
                </div>
            `;
        } else if (status === 'completed') {
            progressHtml = '<span class="positive">100%</span>';
        }
        
        tr.innerHTML = `
            <td>${file.directory || ''}</td>
            <td>${file.filename || ''}</td>
            <td>${size}</td>
            <td>${resolution}</td>
            <td><span class="status-badge status-${status}">${status}</span></td>
            <td>${progressHtml}</td>
            <td>${workerName}</td>
            <td>${savingsHtml}</td>
        `;
        
        tbody.appendChild(tr);
    });
}

// Update summary statistics
function updateSummary() {
    // Count active workers
    const activeWorkers = Object.values(workers).filter(w => 
        w.status === 'idle' || w.status === 'processing'
    ).length;
    
    document.getElementById('active-workers').textContent = activeWorkers;
    
    // Update statistics from stats object
    document.getElementById('total-jobs').textContent = stats.total_files || 0;
    document.getElementById('completed-jobs').textContent = stats.completed_files || 0;
    document.getElementById('processing-jobs').textContent = stats.processing_files || 0;
    document.getElementById('failed-jobs').textContent = stats.failed_files || 0;
    
    const savingsPercent = stats.total_savings_percent || 0;
    document.getElementById('total-savings').textContent = savingsPercent.toFixed(1) + '%';
}

// Utility functions
function formatFileSize(bytes) {
    if (bytes === 0 || !bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return (bytes / Math.pow(k, i)).toFixed(2) + ' ' + sizes[i];
}

function formatDuration(seconds) {
    if (!seconds) return '-';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return `${h}h ${m}m ${s}s`;
}

// Auto-refresh every 5 seconds as backup to WebSocket
setInterval(() => {
    loadInitialData();
}, 5000);

// Initial load
loadInitialData();
