// Global Variables
let currentSessionId = null;
let websocket = null;
let isProcessingResponse = false;
let CLIENT_ID = generateClientId();
let allDocuments = [];
let processingDocuments = new Set(); // Keep track of documents being processed

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Bootstrap components
    initializeBootstrap();
    
    // Set up event listeners
    setupEventListeners();
    
    // Check if we have a stored session
    const storedSessionId = localStorage.getItem('sageX3SessionId');
    if (storedSessionId) {
        // Resume existing session
        currentSessionId = storedSessionId;
        startChat(currentSessionId);
    }
    
    // Preload model (making sure it's ready when needed)
    preloadModel();
    
    console.log('Application initialized with client ID:', CLIENT_ID);
});

// Initialize Bootstrap components
function initializeBootstrap() {
    // Initialize all tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Set up event listeners for the UI
function setupEventListeners() {
    // Upload buttons
    document.getElementById('uploadBtn').addEventListener('click', openUploadModal);
    document.getElementById('uploadInChatBtn').addEventListener('click', openUploadModal);
    document.getElementById('submitUploadBtn').addEventListener('click', handleDocumentUpload);
    
    // Start chat button
    document.getElementById('welcomeStartBtn').addEventListener('click', createNewSession);
    
    // Chat controls
    document.getElementById('messageForm').addEventListener('submit', sendMessage);
    document.getElementById('refreshChatBtn').addEventListener('click', refreshChat);
    
    // Auto-resize textarea
    const messageInput = document.getElementById('messageInput');
    messageInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
        
        // Limit to 5 rows
        const lineHeight = parseInt(getComputedStyle(this).lineHeight);
        const maxHeight = lineHeight * 5;
        if (this.scrollHeight > maxHeight) {
            this.style.height = maxHeight + 'px';
            this.style.overflowY = 'auto';
        } else {
            this.style.overflowY = 'hidden';
        }
    });
    
    // Focus input when clicking message area
    document.getElementById('chatMessages').addEventListener('click', function() {
        if (!isProcessingResponse) {
            messageInput.focus();
        }
    });
}

// Create a new chat session
async function createNewSession() {
    try {
        const response = await fetch('/api/sessions/create', {
            method: 'POST'
        });
        
        if (!response.ok) {
            throw new Error('Failed to create session');
        }
        
        const result = await response.json();
        currentSessionId = result.session_id;
        
        // Store session ID in local storage
        localStorage.setItem('sageX3SessionId', currentSessionId);
        
        // Start chat with new session
        startChat(currentSessionId);
        
    } catch (error) {
        console.error('Error creating session:', error);
        showError('Failed to create a new session. Please try again.');
    }
}

// Start chat with existing session
async function startChat(sessionId) {
    // Show chat screen, hide welcome screen
    document.getElementById('welcomeScreen').style.display = 'none';
    document.getElementById('chatScreen').style.display = 'flex';
    
    // Load documents for this session
    await loadSessionDocuments(sessionId);
    
    // Connect to WebSocket
    connectWebSocket(sessionId);
}

// Open the upload modal
function openUploadModal() {
    // If we don't have a session yet, create one
    if (!currentSessionId) {
        createNewSession().then(() => {
            showUploadModal();
        });
    } else {
        showUploadModal();
    }
}

function showUploadModal() {
    const uploadModal = new bootstrap.Modal(document.getElementById('uploadModal'));
    
    // Reset the form
    document.getElementById('uploadForm').reset();
    document.querySelector('.upload-progress').style.display = 'none';
    document.getElementById('uploadProgressBar').style.width = '0%';
    document.getElementById('uploadStatusText').textContent = 'Uploading document...';
    
    uploadModal.show();
}

// Handle document upload
async function handleDocumentUpload() {
    const fileInput = document.getElementById('documentFile');
    const nameInput = document.getElementById('documentName');
    
    // Validate file
    if (!fileInput.files || fileInput.files.length === 0) {
        showError('Please select a file to upload.');
        return;
    }
    
    const file = fileInput.files[0];
    
    // Get file extension and validate
    const fileExt = file.name.split('.').pop().toLowerCase();
    const supportedExtensions = ['pdf', 'png', 'jpg', 'jpeg', 'tiff', 'bmp', 'gif'];
    
    if (!supportedExtensions.includes(fileExt)) {
        showError(`Unsupported file type. Supported types: ${supportedExtensions.join(', ')}`);
        return;
    }
    
    // Validate file size (max 50MB)
    if (file.size > 50 * 1024 * 1024) {
        showError('File size exceeds the maximum limit of 50MB.');
        return;
    }
    
    // Ensure we have a session
    if (!currentSessionId) {
        try {
            await createNewSession();
        } catch (error) {
            showError('Failed to create a new session. Please try again.');
            return;
        }
    }
    
    // Prepare form data
    const formData = new FormData();
    formData.append('file', file);
    formData.append('session_id', currentSessionId);
    
    // Add custom name if provided
    const customName = nameInput.value.trim();
    if (customName) {
        formData.append('filename', customName);
    }
    
    // Show progress UI
    document.querySelector('.upload-progress').style.display = 'block';
    document.getElementById('submitUploadBtn').disabled = true;
    
    try {
        // Upload the document
        const response = await fetch('/api/documents/upload', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error('Upload failed: ' + (await response.text()));
        }
        
        const result = await response.json();
        
        // Update progress
        document.getElementById('uploadProgressBar').style.width = '100%';
        document.getElementById('uploadStatusText').textContent = 'Upload complete! Processing document...';
        
        // Close upload modal
        bootstrap.Modal.getInstance(document.getElementById('uploadModal')).hide();
        
        // Show processing modal
        showProcessingModal(customName || file.name, result.document_id);
        
        // Start checking document status
        processingDocuments.add(result.document_id);
        checkDocumentStatus(result.document_id);
        
        // If the chat screen isn't shown yet, show it
        if (document.getElementById('chatScreen').style.display === 'none') {
            startChat(currentSessionId);
        } else {
            // Refresh document list
            loadSessionDocuments(currentSessionId);
        }
        
    } catch (error) {
        console.error('Upload error:', error);
        document.querySelector('.upload-progress').style.display = 'none';
        document.getElementById('submitUploadBtn').disabled = false;
        showError('Failed to upload document: ' + error.message);
    }
}

// Show processing modal
function showProcessingModal(documentName, documentId) {
    const processingModal = new bootstrap.Modal(document.getElementById('processingModal'));
    document.getElementById('processingDocumentName').textContent = documentName;
    document.getElementById('processingProgressBar').style.width = '0%';
    document.getElementById('processingPageCount').textContent = 'Page 0 of 0';
    processingModal.show();
    
    // Store the document ID for status checks
    processingModal._documentId = documentId;
}

// Check document processing status
async function checkDocumentStatus(documentId) {
    // Set up interval to check status every 3 seconds
    const statusCheckFunc = async () => {
        try {
            const response = await fetch(`/api/documents/${documentId}/status`);
            
            if (!response.ok) {
                throw new Error('Failed to get document status');
            }
            
            const status = await response.json();
            
            // Calculate page progress if available
            let progressPercentage = 0;
            let pageInfo = '';
            
            if (status.total_pages && status.total_pages > 0) {
                progressPercentage = Math.round((status.processed_pages / status.total_pages) * 100);
                pageInfo = `Page ${status.processed_pages} of ${status.total_pages}`;
            }
            
            // Ensure progress is at least 5% to show some activity
            progressPercentage = Math.max(5, progressPercentage);
            
            // Update processing modal status
            document.getElementById('processingProgressBar').style.width = `${progressPercentage}%`;
            document.getElementById('processingPageCount').textContent = pageInfo;
            document.getElementById('processingStatusText').textContent = 
                status.status === 'processing' ? 'Extracting and analyzing document content...' :
                status.status === 'completed' ? 'Processing complete!' : 
                'Processing failed: ' + (status.error || 'Unknown error');
            
            // Handle completed or failed status
            if (status.status === 'completed' || status.status === 'failed') {
                // Remove from processing set
                processingDocuments.delete(documentId);
                
                // If no more processing documents, close modal
                if (processingDocuments.size === 0) {
                    setTimeout(() => {
                        const modal = bootstrap.Modal.getInstance(document.getElementById('processingModal'));
                        if (modal) {
                            modal.hide();
                        }
                        
                        // Reload documents
                        loadSessionDocuments(currentSessionId);
                    }, 1000);
                }
                
                // Stop checking this document
                return true;
            }
            
            // Continue checking
            return false;
                
        } catch (error) {
            console.error('Status check error:', error);
            // Continue checking in case of errors
            return false;
        }
    };
    
    // Do initial check
    const isComplete = await statusCheckFunc();
    if (!isComplete) {
        // Set interval if not complete
        const interval = setInterval(async () => {
            const isComplete = await statusCheckFunc();
            if (isComplete) {
                clearInterval(interval);
            }
        }, 3000);
    }
}
    
// Load documents for a session
async function loadSessionDocuments(sessionId) {
    const loadingIndicator = document.getElementById('documentsLoadingIndicator');
    const documentList = document.getElementById('documentList');
    
    try {
        loadingIndicator.style.display = 'flex';
        
        const response = await fetch(`/api/sessions/${sessionId}/documents`);
        
        if (!response.ok) {
            throw new Error('Failed to load session documents');
        }
        
        const result = await response.json();
        allDocuments = result.documents || [];
        
        // Clear and populate document list
        // Keep the loading indicator element
        while (documentList.children.length > 1) {
            documentList.removeChild(documentList.lastChild);
        }
        
        if (allDocuments.length === 0) {
            const emptyMessage = document.createElement('div');
            emptyMessage.className = 'text-center text-muted my-4';
            emptyMessage.innerHTML = `
                <i class="bi bi-inbox-fill" style="font-size: 2rem;"></i>
                <p class="mt-2">No documents yet</p>
                <p class="small">Upload documents to start</p>
            `;
            documentList.appendChild(emptyMessage);
            
            // Update document count badge
            document.getElementById('documentCount').textContent = '0 documents';
        } else {
            // Sort by creation date, newest first
            allDocuments.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
            
            // Add each document to the list
            allDocuments.forEach(doc => {
                const docItem = createDocumentListItem(doc);
                documentList.appendChild(docItem);
            });
            
            // Update document count badge
            document.getElementById('documentCount').textContent = 
                `${allDocuments.length} ${allDocuments.length === 1 ? 'document' : 'documents'}`;
        }
        
    } catch (error) {
        console.error('Load documents error:', error);
        showError('Failed to load documents: ' + error.message);
    } finally {
        loadingIndicator.style.display = 'none';
    }
}
    
// Create a document list item
function createDocumentListItem(doc) {
    const docItem = document.createElement('div');
    docItem.className = 'document-item';
    docItem.dataset.id = doc.id;
    
    // Create formatted date
    const createdDate = new Date(doc.created_at);
    const dateStr = createdDate.toLocaleDateString();
    
    // Set badge class based on status
    const badgeClass = 
        doc.status === 'completed' ? 'badge-completed' :
        doc.status === 'processing' ? 'badge-processing' :
        'badge-failed';
    
    // Create progress info if processing
    let progressInfo = '';
    if (doc.status === 'processing' && doc.total_pages > 0) {
        const progressPercent = Math.round((doc.processed_pages / doc.total_pages) * 100);
        progressInfo = `
            <div class="progress mt-1" style="height: 5px;">
                <div class="progress-bar" role="progressbar" style="width: ${progressPercent}%;" 
                     aria-valuenow="${progressPercent}" aria-valuemin="0" aria-valuemax="100"></div>
            </div>
            <small class="text-muted">Page ${doc.processed_pages} of ${doc.total_pages}</small>
        `;
    }
    
    docItem.innerHTML = `
        <div class="document-name">${escapeHtml(doc.filename)}</div>
        <div class="document-meta">
            <span class="badge rounded-pill ${badgeClass}">${doc.status}</span>
            <span class="document-date">${dateStr}</span>
        </div>
        ${progressInfo}
    `;
    
    return docItem;
}

// Connect to WebSocket for chat
function connectWebSocket(sessionId) {
    // Close existing connection if any
    if (websocket && websocket.readyState !== WebSocket.CLOSED) {
        websocket.close();
    }
    
    // Create new WebSocket connection
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/chat/${sessionId}`;
    
    websocket = new WebSocket(wsUrl);
    
    // Connection opened
    websocket.onopen = function(event) {
        console.log('WebSocket connection established');
        
        // Send the initial message with client ID
        websocket.send(JSON.stringify({
            client_id: CLIENT_ID
        }));
    };
    
    // Listen for messages
    websocket.onmessage = function(event) {
        const data = JSON.parse(event.data);
        
        console.log('WebSocket message:', data.status);
        
        if (data.status === 'connected') {
            // Connection confirmed
            console.log('Chat connection established for session', sessionId);
        }
        else if (data.status === 'loading') {
            // Model is loading
            showModelLoading(data.message);
        }
        else if (data.status === 'processing') {
            // Question is being processed
            showTypingIndicator();
        }
        else if (data.status === 'streaming') {
            // Streaming token received
            updateStreamingResponse(data.token);
        }
        else if (data.status === 'complete') {
            // Complete response received
            finishResponse(data.answer, data.time);
        }
        else if (data.status === 'error') {
            // Error received
            handleWebSocketError(data.error);
        }
        else if (data.status === 'heartbeat') {
            // Heartbeat to keep connection alive
            console.log('Heartbeat received');
        }
    };
    
    // Connection closed
    websocket.onclose = function(event) {
        console.log('WebSocket connection closed', event.code, event.reason);
        
        // If not a normal closure and the session is still active, try to reconnect
        if (event.code !== 1000 && currentSessionId === sessionId) {
            console.log('Attempting to reconnect in 3 seconds...');
            setTimeout(() => {
                if (currentSessionId === sessionId) {
                    connectWebSocket(sessionId);
                }
            }, 3000);
        }
    };
    
    // Connection error
    websocket.onerror = function(error) {
        console.error('WebSocket error:', error);
        showError('Connection error. Please try refreshing the page.');
    };
}

// Send a message
function sendMessage(event) {
    event.preventDefault();
    
    const messageInput = document.getElementById('messageInput');
    const question = messageInput.value.trim();
    
    if (!question) {
        return;
    }
    
    // Check if WebSocket is ready
    if (!websocket || websocket.readyState !== WebSocket.OPEN || isProcessingResponse) {
        showError('Cannot send message right now. Please wait or refresh the page.');
        return;
    }
    
    // Add user message to chat
    addUserMessage(question);
    
    // Clear input
    messageInput.value = '';
    messageInput.style.height = 'auto';
    
    // Show typing indicator
    showTypingIndicator();
    
    // Set processing flag
    isProcessingResponse = true;
    
    // Send the message
    try {
        websocket.send(JSON.stringify({
            question: question
        }));
    } catch (error) {
        console.error('Error sending message:', error);
        removeTypingIndicator();
        isProcessingResponse = false;
        
        // Try to reconnect
        showError('Connection error. Attempting to reconnect...');
        connectWebSocket(currentSessionId);
    }
}

// Add user message to chat
function addUserMessage(message) {
    const chatMessages = document.getElementById('chatMessages');
    
    const messageElement = document.createElement('div');
    messageElement.className = 'message user-message';
    
    messageElement.innerHTML = `
        <div class="message-avatar">
            <i class="bi bi-person-fill"></i>
        </div>
        <div class="message-content">
            <p>${escapeHtml(message)}</p>
        </div>
    `;
    
    chatMessages.appendChild(messageElement);
    
    // Scroll to bottom
    scrollToBottom();
}

// Add AI message to chat
function addAiMessage(message) {
    const chatMessages = document.getElementById('chatMessages');
    
    const messageElement = document.createElement('div');
    messageElement.className = 'message';
    messageElement.id = 'current-ai-message';
    
    // Parse markdown in the message
    const parsedMessage = marked.parse(message);
    
    messageElement.innerHTML = `
        <div class="message-avatar">
            <i class="bi bi-robot"></i>
        </div>
        <div class="message-content">
            ${parsedMessage}
        </div>
    `;
    
    chatMessages.appendChild(messageElement);
    
    // Scroll to bottom
    scrollToBottom();
    
    return messageElement;
}

// Show typing indicator
function showTypingIndicator() {
    const chatMessages = document.getElementById('chatMessages');
    
    // Remove existing typing indicator if any
    removeTypingIndicator();
    
    const typingElement = document.createElement('div');
    typingElement.className = 'typing-indicator';
    typingElement.id = 'typing-indicator';
    
    typingElement.innerHTML = `
        <span></span>
        <span></span>
        <span></span>
    `;
    
    chatMessages.appendChild(typingElement);
    
    // Scroll to bottom
    scrollToBottom();
}

// Remove typing indicator
function removeTypingIndicator() {
    const typingIndicator = document.getElementById('typing-indicator');
    if (typingIndicator) {
        typingIndicator.remove();
    }
}

// Show model loading message
function showModelLoading(message) {
    const chatMessages = document.getElementById('chatMessages');
    
    const loadingElement = document.createElement('div');
    loadingElement.className = 'system-message';
    loadingElement.id = 'model-loading';
    
    loadingElement.innerHTML = `
        <div class="message-content">
            <div class="d-flex align-items-center">
                <div class="spinner-border spinner-border-sm text-primary me-2" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mb-0">${message || 'Loading AI model...'}</p>
            </div>
        </div>
    `;
    
    chatMessages.appendChild(loadingElement);
    
    // Scroll to bottom
    scrollToBottom();
}

// Update streaming response
let currentResponseElement = null;
let currentResponseText = '';

function updateStreamingResponse(token) {
    // Remove typing indicator if present
    removeTypingIndicator();
    
    // If this is the first token, create a new message element
    if (!currentResponseElement) {
        currentResponseText = token;
        currentResponseElement = addAiMessage(currentResponseText);
    } else {
        // Update existing message
        currentResponseText += token;
        
        // Parse markdown
        const parsedMessage = marked.parse(currentResponseText);
        
        // Update message content
        const contentElement = currentResponseElement.querySelector('.message-content');
        contentElement.innerHTML = parsedMessage;
    }
    
    // Scroll to bottom
    scrollToBottom();
}

// Finish response
function finishResponse(answer, time) {
    // Remove typing indicator if present
    removeTypingIndicator();
    
    // If we have a streaming response in progress, finalize it
    if (currentResponseElement) {
        // Update content one last time if different
        if (currentResponseText !== answer) {
            currentResponseText = answer;
            const parsedMessage = marked.parse(currentResponseText);
            
            const contentElement = currentResponseElement.querySelector('.message-content');
            contentElement.innerHTML = parsedMessage;
        }
        
        // Add response time if provided
        if (time) {
            const timeElement = document.createElement('div');
            timeElement.className = 'response-time small text-muted mt-2';
            timeElement.textContent = `Response time: ${time.toFixed(2)}s`;
            
            currentResponseElement.querySelector('.message-content').appendChild(timeElement);
        }
        
        // Remove the id so we know it's complete
        currentResponseElement.removeAttribute('id');
    } else {
        // If no streaming response, add the complete message
        const messageElement = addAiMessage(answer);
        
        // Add response time if provided
        if (time) {
            const timeElement = document.createElement('div');
            timeElement.className = 'response-time small text-muted mt-2';
            timeElement.textContent = `Response time: ${time.toFixed(2)}s`;
            
            messageElement.querySelector('.message-content').appendChild(timeElement);
        }
    }
    
    // Reset tracking variables
    currentResponseElement = null;
    currentResponseText = '';
    
    // Reset processing flag
    isProcessingResponse = false;
    
    // Scroll to bottom
    scrollToBottom();
    
    // Focus input again
    document.getElementById('messageInput').focus();
}

// Handle WebSocket error
function handleWebSocketError(error) {
    console.error('WebSocket error:', error);
    
    // Remove typing indicator
    removeTypingIndicator();
    
    // Add error message to chat
    const chatMessages = document.getElementById('chatMessages');
    
    const errorElement = document.createElement('div');
    errorElement.className = 'system-message';
    
    errorElement.innerHTML = `
        <div class="message-content">
            <p class="text-danger">
                <i class="bi bi-exclamation-triangle-fill me-2"></i>
                Error: ${escapeHtml(error)}
            </p>
        </div>
    `;
    
    chatMessages.appendChild(errorElement);
    
    // Scroll to bottom
    scrollToBottom();
    
    // Reset processing flag
    isProcessingResponse = false;
}

// Preload model
function preloadModel() {
    fetch('/api/preload-model', {
        method: 'POST'
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Failed to preload model');
        }
        return response.json();
    })
    .then(data => {
        console.log('Model preloaded:', data);
    })
    .catch(error => {
        console.error('Error preloading model:', error);
        // Non-critical error, we can continue
    });
}

// Refresh chat
function refreshChat() {
    if (currentSessionId) {
        // Reset chat and reconnect
        const chatMessages = document.getElementById('chatMessages');
        
        // Clear all messages except the first system message
        while (chatMessages.children.length > 1) {
            chatMessages.removeChild(chatMessages.lastChild);
        }
        
        // Reset variables
        currentResponseElement = null;
        currentResponseText = '';
        isProcessingResponse = false;
        
        // Reconnect WebSocket
        connectWebSocket(currentSessionId);
        
        // Reload documents
        loadSessionDocuments(currentSessionId);
    }
}

// Show error message
function showError(message) {
    const errorModal = new bootstrap.Modal(document.getElementById('errorModal'));
    document.getElementById('errorModalText').textContent = message;
    errorModal.show();
}

// Show info message
function showInfo(message) {
    // Create a toast-like notification
    const toastContainer = document.createElement('div');
    toastContainer.style.position = 'absolute';
    toastContainer.style.top = '20px';
    toastContainer.style.right = '20px';
    toastContainer.style.zIndex = '1050';
    
    toastContainer.innerHTML = `
        <div class="toast show" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header">
                <strong class="me-auto">Information</strong>
                <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
            <div class="toast-body">
                ${escapeHtml(message)}
            </div>
        </div>
    `;
    
    document.body.appendChild(toastContainer);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        toastContainer.remove();
    }, 5000);
    
    // Add click handler to close button
    const closeButton = toastContainer.querySelector('.btn-close');
    closeButton.addEventListener('click', () => {
        toastContainer.remove();
    });
}

// Scroll chat to bottom
function scrollToBottom() {
    const chatMessages = document.getElementById('chatMessages');
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Generate a client ID
function generateClientId() {
    // Check if we already have a client ID in local storage
    const storedClientId = localStorage.getItem('sageX3ClientId');
    if (storedClientId) {
        return storedClientId;
    }
    
    // Generate a new client ID
    const newClientId = 'client_' + Math.random().toString(36).substring(2, 15);
    
    // Store it for future use
    localStorage.setItem('sageX3ClientId', newClientId);
    
    return newClientId;
}

// Escape HTML to prevent XSS
function escapeHtml(unsafe) {
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Format file size for display
function formatFileSize(bytes) {
    if (bytes < 1024) {
        return bytes + ' B';
    } else if (bytes < 1024 * 1024) {
        return (bytes / 1024).toFixed(1) + ' KB';
    } else if (bytes < 1024 * 1024 * 1024) {
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    } else {
        return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB';
    }
}