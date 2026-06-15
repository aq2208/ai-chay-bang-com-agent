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
        ws: null,
        runningJob: null,

        // --- Report Generation States ---
        reportStartTime: '',
        reportEndTime: '',
        isGeneratingReport: false,
        reportGenMessage: '',
        reportGenError: false,

        // --- Initialize App ---
        initApp() {
            this.appendLog("[SYSTEM]: Khởi tạo trung tâm chỉ huy thành công.");
            this.appendLog("[SYSTEM]: Thiết lập định tuyến qua URL Hash: " + this.currentHash);
            
            // Watch currentHash changes to log them
            this.$watch('currentHash', value => {
                this.appendLog("[SYSTEM DEBUG]: Route transition to " + value);
                console.log("[SYSTEM DEBUG]: Route transition to " + value);
            });

            // Lấy báo cáo và lịch sử ban đầu từ API
            this.fetchHistoryAndReports();

            // Kết nối WebSocket để cập nhật trạng thái thời gian thực
            this.initWebSocket();
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
                
                // If it transitions from idle to processing, apply visual screen shake warning
                if (activeJobRunning && !this.isProcessing) {
                    this.isProcessing = true;
                    this.runningJob = isJiraRunning ? 'jira' : 'social';
                    this.triggerScreenShake();
                    this.appendLog(`[SYSTEM LOCK]: Tiến trình cào dữ liệu [${this.runningJob.toUpperCase()}] đang được thực thi ngầm! Khóa nút bấm điều khiển.`);
                    
                    // Keep glass open if it's already running
                    if (isJiraRunning) this.glassOpenA = true;
                    if (isSocialRunning) this.glassOpenB = true;
                } 
                // If it transitions from processing to idle, release the lock and refresh data
                else if (!activeJobRunning && this.isProcessing) {
                    this.isProcessing = false;
                    const finishedJob = this.runningJob || (status.jira.status !== 'idle' ? 'jira' : 'social');
                    const jobDetails = status[finishedJob];
                    
                    if (jobDetails && jobDetails.status === 'error') {
                        this.appendLog(`[SYSTEM ERROR]: Tiến trình cào [${finishedJob.toUpperCase()}] THẤT BẠI. Chi tiết lỗi: ${jobDetails.error || 'Lỗi không xác định'}`);
                    } else {
                        this.appendLog(`[SYSTEM UNLOCK]: Tiến trình cào [${finishedJob.toUpperCase()}] hoàn tất thành công. Giải phóng khóa hệ thống.`);
                    }
                    
                    this.runningJob = null;
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

        // --- Khởi tạo kết nối WebSockets ---
        initWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/status`;
            
            this.appendLog(`[WEBSOCKET]: Đang thiết lập kết nối tới ${wsUrl}...`);
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                this.appendLog("[WEBSOCKET]: Kết nối WebSocket thành công. Đang lắng nghe kênh sự kiện...");
                console.log("[WEBSOCKET]: Connected successfully.");
            };
            
            this.ws.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    if (message.type === 'status') {
                        this.handleStatusUpdate(message.data);
                    }
                } catch (e) {
                    console.error("[WEBSOCKET ERROR]: Không thể phân tích tin nhắn:", e);
                }
            };
            
            this.ws.onclose = (event) => {
                this.appendLog("[WEBSOCKET WARNING]: Mất kết nối WebSocket. Tự động kết nối lại sau 5 giây...");
                console.warn(`[WEBSOCKET]: Connection closed (code: ${event.code}). Reconnecting...`);
                
                if (this.ws) {
                    this.ws = null;
                }
                
                setTimeout(() => {
                    this.initWebSocket();
                }, 5000);
            };
            
            this.ws.onerror = (error) => {
                console.error("[WEBSOCKET ERROR]:", error);
            };
        },

        // --- Xử lý Cập nhật Trạng thái Nhận được từ WS ---
        handleStatusUpdate(status) {
            this.fetchHistoryAndReports();
            const isJiraRunning = status.jira && status.jira.status === 'running';
            const isSocialRunning = status.social && status.social.status === 'running';
            const activeJobRunning = isJiraRunning || isSocialRunning;
            
            // Trường hợp 1: Chuyển sang trạng thái ĐANG CHẠY (Lock màn hình)
            if (activeJobRunning && !this.isProcessing) {
                this.isProcessing = true;
                this.runningJob = isJiraRunning ? 'jira' : 'social';
                this.triggerScreenShake();
                this.appendLog(`[SYSTEM LOCK]: Tiến trình cào [${this.runningJob.toUpperCase()}] đang thực thi ngầm! Khóa giao diện.`);
                
                if (isJiraRunning) this.glassOpenA = true;
                if (isSocialRunning) this.glassOpenB = true;
            } 
            // Trường hợp 2: Chuyển từ ĐANG CHẠY sang RẢNH (Giải phóng lock & Tải lại báo cáo)
            else if (!activeJobRunning && this.isProcessing) {
                this.isProcessing = false;
                const finishedJob = this.runningJob || (status.jira.status !== 'idle' ? 'jira' : 'social');
                const jobDetails = status[finishedJob];
                
                if (jobDetails && jobDetails.status === 'error') {
                    this.appendLog(`[SYSTEM ERROR]: Tiến trình cào [${finishedJob.toUpperCase()}] THẤT BẠI. Lỗi: ${jobDetails.error || 'Lỗi hệ thống'}`);
                } else {
                    this.appendLog(`[SYSTEM UNLOCK]: Tiến trình cào [${finishedJob.toUpperCase()}] hoàn tất thành công. Giải phóng khóa.`);
                }
                
                this.runningJob = null;
                this.fetchHistoryAndReports(); // Tải lại lịch sử và báo cáo AI mới nhất
                
                this.glassOpenA = false;
                this.glassOpenB = false;
            }
        },

        // --- Generate Report from DB posts (date range) ---
        async generateReport() {
            if (this.isGeneratingReport) return;

            if (!this.reportStartTime || !this.reportEndTime) {
                this.reportGenMessage = '[ERROR]: Vui lòng chọn cả Start Data Time và End Data Time.';
                this.reportGenError = true;
                return;
            }

            this.isGeneratingReport = true;
            this.reportGenMessage = '';
            this.reportGenError = false;

            const startIso = new Date(this.reportStartTime).toISOString();
            const endIso = new Date(this.reportEndTime).toISOString();

            this.appendLog(`[REPORT]: Gửi yêu cầu tạo báo cáo từ ${this.reportStartTime} → ${this.reportEndTime}...`);

            try {
                const res = await fetch('/api/reports/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        start_data_time: startIso,
                        end_data_time: endIso,
                    })
                });

                const data = await res.json();

                if (!res.ok) {
                    throw new Error(data.detail || data.message || 'Lỗi không xác định.');
                }

                if (data.count === 0) {
                    this.reportGenMessage = `[INFO]: ${data.message}`;
                    this.reportGenError = false;
                    this.appendLog(`[REPORT]: ${data.message}`);
                } else {
                    this.reportGenMessage = `[SUCCESS]: ${data.message} — Báo cáo đang được tạo nền, hãy nhấn REFRESH sau vài giây.`;
                    this.reportGenError = false;
                    this.appendLog(`[REPORT]: Đang tạo báo cáo từ ${data.count} bài đăng...`);
                }
            } catch (err) {
                this.reportGenMessage = `[ERROR]: ${err.message}`;
                this.reportGenError = true;
                this.appendLog(`[REPORT ERROR]: ${err.message}`);
            } finally {
                this.isGeneratingReport = false;
            }
        },

        // --- Trigger Crawling ---
        async triggerCrawl(jobType) {
            if (this.isProcessing) return;

            this.appendLog(`[PROTOCOL]: Chuẩn bị kích hoạt hủy diệt thế giới qua cổng ${jobType.toUpperCase()}...`);
            this.isProcessing = true;
            this.runningJob = jobType;
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
        },

        // --- Render Markdown to HTML using marked.js ---
        renderMarkdown(content) {
            if (!content) return '';
            if (typeof marked === 'undefined') return this.escapeHtml(content);
            try {
                return marked.parse(content);
            } catch (e) {
                console.error('[MD]: Failed to parse markdown:', e);
                return this.escapeHtml(content);
            }
        }
    }
}
