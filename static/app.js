document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('configForm');
    const startBtn = document.getElementById('startBtn');
    const btnText = startBtn.querySelector('.btn-text');
    const spinner = startBtn.querySelector('.spinner');
    const consoleOutput = document.getElementById('consoleOutput');
    const stopBtn = document.getElementById('stopBtn');
    
    let ws = null;

    // Helper to add lines to the terminal
    function appendLog(message, isSystem = false) {
        const div = document.createElement('div');
        div.className = 'log-line';
        if (isSystem) div.classList.add('system-msg');
        
        // Basic color coding for the terminal logs
        if (message.includes('[+]') || message.includes('[✓]')) {
            div.style.color = '#34d399'; // Green
        } else if (message.includes('[!]') || message.includes('[-]')) {
            div.style.color = '#f87171'; // Red
        } else if (message.includes('[*]')) {
            div.style.color = '#60a5fa'; // Blue
        } else if (message.includes('[AI]')) {
            div.style.color = '#c084fc'; // Purple
        } else {
            div.style.color = '#e5e7eb'; // Default white/gray
        }

        div.textContent = message;
        consoleOutput.appendChild(div);
        
        // Auto-scroll to bottom
        consoleOutput.scrollTop = consoleOutput.scrollHeight;
    }

    stopBtn.addEventListener('click', () => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            appendLog('Stopping agent manually...', true);
            ws.send(JSON.stringify({ action: 'stop' }));
        }
    });

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;
        const apiKey = document.getElementById('apiKey').value;

        // UI State update
        startBtn.style.display = 'none';
        stopBtn.style.display = 'block';
        btnText.textContent = 'Connecting...';
        spinner.classList.remove('hidden');
        
        appendLog('Initializing connection to backend agent...', true);

        // Determine correct WebSocket protocol (ws:// or wss://)
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/logs`;
        
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            appendLog('Connection established. Sending secure configuration...', true);
            // Send config
            ws.send(JSON.stringify({ username, password, apiKey }));
            btnText.textContent = 'Agent Running';
        };

        ws.onmessage = (event) => {
            appendLog(event.data);
        };

        ws.onclose = () => {
            appendLog('Connection closed. Automation ended or disconnected.', true);
            // Reset UI
            startBtn.disabled = false;
            startBtn.style.display = 'block';
            stopBtn.style.display = 'none';
            btnText.textContent = 'Start Automation';
            spinner.classList.add('hidden');
        };

        ws.onerror = (error) => {
            appendLog('WebSocket error occurred. Is the backend running?', true);
            console.error(error);
        };
    });
});
