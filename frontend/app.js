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
        reports: [],
        ws: null,
        runningJob: null,
        chart: null,

        // --- Report Generation States ---
        reportStartTime: '',
        reportEndTime: '',
        isGeneratingReport: false,
        reportGenMessage: '',
        reportGenError: false,
        pendingReportId: null,   // track the in-flight report for WS auto-open

        // --- Report Preview Modal States ---
        reportModalOpen: false,
        reportModalContent: '',
        reportModalMeta: null,   // { id, report_type, status, created_at, start_data_time, end_data_time }
        reportModalLoading: false,

        // --- Initialize App ---
        initApp() {
            this.appendLog("[SYSTEM]: Khởi tạo trung tâm chỉ huy thành công.");
            this.appendLog("[SYSTEM]: Thiết lập định tuyến qua URL Hash: " + this.currentHash);

            // Watch currentHash changes to log them
            this.$watch('currentHash', value => {
                this.appendLog("[SYSTEM DEBUG]: Route transition to " + value);
                console.log("[SYSTEM DEBUG]: Route transition to " + value);
                if (value === '#dashboard') {
                    this.fetchChartData();
                    this.fetchReports();
                }
            });

            // Initial data fetch
            this.fetchHistory();
            this.fetchReports();
            if (this.currentHash === '#dashboard') {
                this.fetchChartData();
            }

            // Connect WebSocket for real-time updates
            this.initWebSocket();
        },

        // --- Fetch Current Crawling Status (Lock check) ---
        async fetchStatus() {
            try {
                const response = await fetch('/status');
                if (!response.ok) throw new Error('Không thể lấy trạng thái hệ thống.');
                const status = await response.json();

                const isJiraRunning = status.jira && status.jira.status === 'running';
                const isSocialRunning = status.social && status.social.status === 'running';
                const activeJobRunning = isJiraRunning || isSocialRunning;

                if (activeJobRunning && !this.isProcessing) {
                    this.isProcessing = true;
                    this.runningJob = isJiraRunning ? 'jira' : 'social';
                    this.triggerScreenShake();
                    this.appendLog(`[SYSTEM LOCK]: Tiến trình cào dữ liệu [${this.runningJob.toUpperCase()}] đang được thực thi ngầm! Khóa nút bấm điều khiển.`);
                    if (isJiraRunning) this.glassOpenA = true;
                    if (isSocialRunning) this.glassOpenB = true;
                } else if (!activeJobRunning && this.isProcessing) {
                    this.isProcessing = false;
                    const finishedJob = this.runningJob || (status.jira.status !== 'idle' ? 'jira' : 'social');
                    const jobDetails = status[finishedJob];

                    if (jobDetails && jobDetails.status === 'error') {
                        this.appendLog(`[SYSTEM ERROR]: Tiến trình cào [${finishedJob.toUpperCase()}] THẤT BẠI. Chi tiết lỗi: ${jobDetails.error || 'Lỗi không xác định'}`);
                    } else {
                        this.appendLog(`[SYSTEM UNLOCK]: Tiến trình cào [${finishedJob.toUpperCase()}] hoàn tất thành công. Giải phóng khóa hệ thống.`);
                    }

                    this.runningJob = null;
                    this.fetchHistory();
                    this.glassOpenA = false;
                    this.glassOpenB = false;
                }
            } catch (err) {
                console.error(err);
            }
        },

        // --- Fetch Crawl History ---
        async fetchHistory() {
            try {
                const histRes = await fetch('/api/history');
                if (histRes.ok) {
                    this.history = await histRes.json();
                }
            } catch (err) {
                this.appendLog("[ERROR]: Lỗi khi lấy lịch sử từ Database: " + err.message);
            }
        },

        // --- Fetch All AI Reports (list, no content) ---
        async fetchReports() {
            try {
                const res = await fetch('/api/reports');
                if (res.ok) {
                    this.reports = await res.json();
                }
            } catch (err) {
                this.appendLog("[ERROR]: Lỗi khi lấy danh sách báo cáo: " + err.message);
            }
        },

        // --- View a Single Report (opens modal) ---
        async viewReport(id) {
            this.reportModalOpen = true;
            this.reportModalLoading = true;
            this.reportModalContent = '';
            this.reportModalMeta = null;
            try {
                const res = await fetch(`/api/reports/${id}`);
                if (!res.ok) throw new Error('Không thể tải báo cáo.');
                const data = await res.json();
                this.reportModalMeta = {
                    id: data.id,
                    report_type: data.report_type,
                    status: data.status,
                    created_at: data.created_at,
                    start_data_time: data.start_data_time,
                    end_data_time: data.end_data_time,
                };
                this.reportModalContent = data.content || '';
            } catch (err) {
                this.reportModalContent = `[ERROR]: ${err.message}`;
            } finally {
                this.reportModalLoading = false;
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
                    } else if (message.type === 'report_update') {
                        this.handleReportUpdate(message.data);
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

        // --- Handle Crawl Status Update from WS ---
        handleStatusUpdate(status) {
            this.fetchHistory();
            const isJiraRunning = status.jira && status.jira.status === 'running';
            const isSocialRunning = status.social && status.social.status === 'running';
            const activeJobRunning = isJiraRunning || isSocialRunning;

            if (activeJobRunning && !this.isProcessing) {
                this.isProcessing = true;
                this.runningJob = isJiraRunning ? 'jira' : 'social';
                this.triggerScreenShake();
                this.appendLog(`[SYSTEM LOCK]: Tiến trình cào [${this.runningJob.toUpperCase()}] đang thực thi ngầm! Khóa giao diện.`);
                if (isJiraRunning) this.glassOpenA = true;
                if (isSocialRunning) this.glassOpenB = true;
            } else if (!activeJobRunning && this.isProcessing) {
                this.isProcessing = false;
                const finishedJob = this.runningJob || (status.jira.status !== 'idle' ? 'jira' : 'social');
                const jobDetails = status[finishedJob];

                if (jobDetails && jobDetails.status === 'error') {
                    this.appendLog(`[SYSTEM ERROR]: Tiến trình cào [${finishedJob.toUpperCase()}] THẤT BẠI. Lỗi: ${jobDetails.error || 'Lỗi hệ thống'}`);
                } else {
                    this.appendLog(`[SYSTEM UNLOCK]: Tiến trình cào [${finishedJob.toUpperCase()}] hoàn tất thành công. Giải phóng khóa.`);
                }

                this.runningJob = null;
                this.glassOpenA = false;
                this.glassOpenB = false;
            }
        },

        // --- Handle Report Status Update from WS ---
        handleReportUpdate(data) {
            const { report_id, status } = data;
            this.appendLog(`[REPORT]: Báo cáo #${report_id} → ${status}`);

            // Refresh reports list to show updated status
            this.fetchReports();

            // Auto-open preview if this is the pending report and it's done
            if (this.pendingReportId === report_id && status === 'DONE') {
                this.pendingReportId = null;
                this.reportGenMessage = '';
                this.appendLog(`[REPORT]: Báo cáo #${report_id} hoàn tất! Đang mở xem trước...`);
                this.viewReport(report_id);
            } else if (this.pendingReportId === report_id && status === 'ERROR') {
                this.pendingReportId = null;
                this.reportGenMessage = `[ERROR]: Tạo báo cáo #${report_id} thất bại.`;
                this.reportGenError = true;
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

            const startIso = new Date(this.reportStartTime + 'T00:00:00').toISOString();
            const endIso = new Date(this.reportEndTime + 'T23:59:59').toISOString();

            this.appendLog(`[REPORT]: Gửi yêu cầu tạo báo cáo từ ${this.reportStartTime} (00:00) → ${this.reportEndTime} (23:59)...`);

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
                    // Store report_id to track via WebSocket
                    this.pendingReportId = data.report_id;
                    this.reportGenMessage = `[RUNNING]: Báo cáo #${data.report_id} đang được tạo từ ${data.count} bài đăng. Kiểm tra bảng bên dưới — báo cáo sẽ tự động mở khi hoàn tất.`;
                    this.reportGenError = false;
                    this.appendLog(`[REPORT]: Báo cáo #${data.report_id} RUNNING — đang xử lý ${data.count} bài đăng...`);
                    // Refresh list to show the new RUNNING row immediately
                    this.fetchReports();
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
            if (!isoString) return '—';
            try {
                const d = new Date(isoString);
                return d.toLocaleString('vi-VN');
            } catch (e) {
                return isoString;
            }
        },

        // --- Format Date only (no time) ---
        formatDateOnly(isoString) {
            if (!isoString) return '—';
            try {
                const d = new Date(isoString);
                return d.toLocaleDateString('vi-VN');
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
        },

        // --- Fetch Daily Complaint Data for Chart ---
        async fetchChartData() {
            try {
                this.appendLog("[CHART]: Đang tải dữ liệu biểu đồ khiếu nại hàng ngày...");
                const response = await fetch('/api/complaints/daily');
                if (!response.ok) throw new Error('Không thể tải dữ liệu biểu đồ.');
                const data = await response.json();
                this.renderChart(data);
                this.appendLog("[CHART]: Đã cập nhật dữ liệu biểu đồ thành công.");
            } catch (err) {
                this.appendLog("[ERROR]: Lỗi khi lấy dữ liệu biểu đồ: " + err.message);
            }
        },

        // --- Render Line Chart using Chart.js ---
        renderChart(data) {
            const ctx = document.getElementById('complaintsChart');
            if (!ctx) return;

            const labels = data.map(d => d.date);
            const threadsData = data.map(d => d.threads || 0);
            const jiraData = data.map(d => d.jira || 0);
            const appStoreData = data.map(d => d.app_store || 0);

            if (this.chart) {
                this.chart.data.labels = labels;
                this.chart.data.datasets[0].data = threadsData;
                this.chart.data.datasets[1].data = jiraData;
                this.chart.data.datasets[2].data = appStoreData;
                this.chart.update();
            } else {
                if (typeof Chart === 'undefined') {
                    console.error('Chart.js is not loaded yet');
                    return;
                }
                this.chart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [
                            {
                                label: 'Threads',
                                data: threadsData,
                                borderColor: '#06b6d4',
                                backgroundColor: 'rgba(6, 182, 212, 0.05)',
                                borderWidth: 2,
                                tension: 0.35,
                                fill: true,
                                pointBackgroundColor: '#06b6d4',
                                pointBorderColor: '#0f172a',
                                pointHoverRadius: 6
                            },
                            {
                                label: 'Jira',
                                data: jiraData,
                                borderColor: '#ef4444',
                                backgroundColor: 'rgba(239, 68, 68, 0.05)',
                                borderWidth: 2,
                                tension: 0.35,
                                fill: true,
                                pointBackgroundColor: '#ef4444',
                                pointBorderColor: '#0f172a',
                                pointHoverRadius: 6
                            },
                            {
                                label: 'App Store Review',
                                data: appStoreData,
                                borderColor: '#22c55e',
                                backgroundColor: 'rgba(34, 197, 94, 0.05)',
                                borderWidth: 2,
                                tension: 0.35,
                                fill: true,
                                pointBackgroundColor: '#22c55e',
                                pointBorderColor: '#0f172a',
                                pointHoverRadius: 6
                            }
                        ]
                    },
                    plugins: [{
                        id: 'chartLetterSpacing',
                        beforeDraw(chart) {
                            if (chart.ctx && 'letterSpacing' in chart.ctx) {
                                chart.ctx.letterSpacing = '2.5px';
                            }
                        },
                        afterDraw(chart) {
                            if (chart.ctx && 'letterSpacing' in chart.ctx) {
                                chart.ctx.letterSpacing = '0px';
                            }
                        }
                    }],
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                labels: {
                                    color: '#94a3b8',
                                    font: {
                                        family: 'Orbitron',
                                        size: 12,
                                        weight: '500'
                                    }
                                }
                            },
                            tooltip: {
                                mode: 'index',
                                intersect: false,
                                backgroundColor: '#0f172a',
                                titleColor: '#38bdf8',
                                titleFont: { family: 'Orbitron' },
                                bodyFont: { family: 'Share Tech Mono' },
                                borderColor: '#334155',
                                borderWidth: 1
                            }
                        },
                        scales: {
                            x: {
                                grid: { color: 'rgba(51, 65, 85, 0.15)' },
                                ticks: {
                                    color: '#94a3b8',
                                    font: { family: 'Share Tech Mono' }
                                }
                            },
                            y: {
                                grid: { color: 'rgba(51, 65, 85, 0.15)' },
                                ticks: {
                                    color: '#94a3b8',
                                    font: { family: 'Share Tech Mono' },
                                    stepSize: 1,
                                    precision: 0
                                }
                            }
                        }
                    }
                });
            }
        }
    }
}
