/**
 * Zalopay Complaint Analytics — App JS Controller (Alpine.js integration)
 */

function appState() {
    return {
        // --- Navigation Routing ---
        currentHash: window.location.hash || '#crawler',

        // --- UI States ---
        glassOpenA: false,
        glassOpenB: false,
        isProcessing: false,
        errorModalOpen: false,
        errorModalContent: '',
        copied: false,

        // --- Data States ---
        history: [],
        latestReport: null,
        pollingInterval: null,

        // --- Initialize App ---
        initApp() {
            this.appendLog("[SYSTEM]: Khởi tạo trung tâm chỉ huy thành công.");
            this.appendLog("[SYSTEM]: Thiết lập định tuyến qua URL Hash: " + this.currentHash);
            
            // Initial fetch of logs and status
            this.fetchStatus();
            this.fetchHistoryAndReports();

            // Set up polling every 3 seconds to check for concurrency locking status
            this.pollingInterval = setInterval(() => {
                this.fetchStatus();
            }, 3000);
        },

        // --- Fetch Current Crawling Status (Lock check) ---
        async fetchStatus() {
            try {
                const response = await fetch('/status');
                if (!response.ok) throw new Error('Không thể lấy trạng thái hệ thống.');
                const status = await response.json();
                
                // Check if either JIRA or SOCIAL job is currently running
                const isJiraRunning = status.jira && status.jira.status === 'running';
                const isSocialRunning = status.social && status.social.status === 'running';
                
                const activeJobRunning = isJiraRunning || isSocialRunning;
                
                // If it transition from idle to processing, apply visual screen shake warning
                if (activeJobRunning && !this.isProcessing) {
                    this.isProcessing = true;
                    this.triggerScreenShake();
                    this.appendLog(`[SYSTEM LOCK]: Tiến trình cào dữ liệu đang được thực thi ngầm! Khóa nút bấm điều khiển.`);
                    
                    // Keep glass open if it's already running
                    if (isJiraRunning) this.glassOpenA = true;
                    if (isSocialRunning) this.glassOpenB = true;
                } 
                // If it transitions from processing to idle, release the lock and refresh data
                else if (!activeJobRunning && this.isProcessing) {
                    this.isProcessing = false;
                    this.appendLog("[SYSTEM UNLOCK]: Tiến trình hoàn tất. Giải phóng khóa hệ thống.");
                    this.fetchHistoryAndReports();
                    // Close glass covers
                    this.glassOpenA = false;
                    this.glassOpenB = false;
                }
            } catch (err) {
                console.error(err);
            }
        },

        // --- Fetch Crawl History and AI Reports ---
        async fetchHistoryAndReports() {
            try {
                // Fetch history
                const histRes = await fetch('/api/history');
                if (histRes.ok) {
                    this.history = await histRes.json();
                }

                // Fetch latest report
                const repRes = await fetch('/api/reports/latest');
                if (repRes.ok) {
                    const data = await repRes.json();
                    this.latestReport = data.report || null;
                }
            } catch (err) {
                this.appendLog("[ERROR]: Lỗi khi lấy lịch sử/báo cáo từ Database: " + err.message);
            }
        },

        // --- Trigger Crawling ---
        async triggerCrawl(jobType) {
            if (this.isProcessing) return;

            this.appendLog(`[PROTOCOL]: Chuẩn bị kích hoạt hủy diệt thế giới qua cổng ${jobType.toUpperCase()}...`);
            this.isProcessing = true;
            this.triggerScreenShake();

            // Dramatic matrix countdown simulation
            for (let i = 3; i > 0; i--) {
                this.appendLog(`[WARNING]: Tự động cào dữ liệu bắt đầu sau ${i}...`);
                await new Promise(r => setTimeout(r, 600));
            }

            this.appendLog(`[DEPLOY]: Đang gửi lệnh POST /run/${jobType} đến Backend...`);

            try {
                const response = await fetch(`/run/${jobType}?dry_run=false`, {
                    method: 'POST'
                });
                
                const result = await response.json();
                
                if (!response.ok) {
                    throw new Error(result.message || 'Lỗi bất ngờ xảy ra.');
                }
                
                this.appendLog(`[SUCCESS]: ${result.message}`);
                this.appendLog(`[INFO]: Đang chạy ngầm ở Backend. Hãy theo dõi History Logs.`);
                
            } catch (err) {
                this.appendLog(`[API ERROR]: Không thể kích hoạt cào dữ liệu: ${err.message}`);
                this.isProcessing = false;
            }
        },

        // --- Screenshake & Alert Blinking Trigger ---
        triggerScreenShake() {
            const body = document.body;
            body.classList.add('shake-effect');
            setTimeout(() => {
                body.classList.remove('shake-effect');
            }, 1200);
        },

        // --- Append Message to Terminal Log ---
        appendLog(message) {
            const container = document.getElementById('terminal-logs');
            if (!container) return;
            
            const timestamp = new Date().toLocaleTimeString();
            const div = document.createElement('div');
            div.innerHTML = `<span class="text-cyan-500">[${timestamp}]</span> ${this.escapeHtml(message)}`;
            container.appendChild(div);
            container.scrollTop = container.scrollHeight;
        },

        // --- Format Timestamps ---
        formatDate(isoString) {
            if (!isoString) return '';
            try {
                const d = new Date(isoString);
                return d.toLocaleString('vi-VN');
            } catch (e) {
                return isoString;
            }
        },

        // --- Show Detailed Error Modal ---
        showErrorModal(errText) {
            this.errorModalContent = errText;
            this.errorModalOpen = true;
            this.copied = false;
        },

        // --- Copy Error Log to Clipboard ---
        async copyErrorToClipboard() {
            try {
                await navigator.clipboard.writeText(this.errorModalContent);
                this.copied = true;
                this.appendLog("[SYSTEM]: Đã sao chép log lỗi vào clipboard.");
                setTimeout(() => { this.copied = false; }, 2000);
            } catch (err) {
                this.appendLog("[ERROR]: Không thể sao chép: " + err.message);
            }
        },

        // --- Helper to escape HTML ---
        escapeHtml(str) {
            return str
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;");
        }
    }
}
