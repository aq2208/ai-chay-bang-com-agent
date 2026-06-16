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
        reportStartTime: (() => { const d = new Date(); d.setDate(d.getDate() - 7); return d.toISOString().slice(0, 10); })(),
        reportEndTime: new Date().toISOString().slice(0, 10),
        isGeneratingReport: false,
        reportGenMessage: '',
        reportGenError: false,
        pendingReportId: null,   // track the in-flight report for WS auto-open

        // --- Report Preview Modal States ---
        reportModalOpen: false,
        reportModalContent: '',
        reportModalMeta: null,   // { id, report_type, status, created_at, start_data_time, end_data_time }
        reportModalLoading: false,
        reportCopied: false,
        reportShared: false,

        // --- Image Lightbox States ---
        imgLightboxOpen: false,
        imgLightboxSrc: '',
        imgLightboxScale: 1,
        imgLightboxNaturalW: 0,

        // --- Superman Easter Egg State ---
        supermanRunning: false,

        // --- Initialize App ---
        initApp() {
            this.appendLog("[SYSTEM]: Khởi tạo trung tâm chỉ huy thành công.");
            this.appendLog("[SYSTEM]: Thiết lập định tuyến qua URL Hash: " + this.currentHash);

            // Watch currentHash changes to log them
            this.$watch('currentHash', value => {
                this.appendLog("[SYSTEM DEBUG]: Route transition to " + value);
                console.log("[SYSTEM DEBUG]: Route transition to " + value);
                if (value === '#dashboard') {
                    // Destroy stale chart instance before re-rendering — canvas loses
                    // its 2D context when hidden via display:none (x-show), so update()
                    // on the cached instance silently no-ops and hover/tooltips break.
                    if (this.chart) {
                        this.chart.destroy();
                        this.chart = null;
                    }
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

            // Configure marked renderers once at startup
            this.initMarkdown();

            // Deep-link: auto-open report modal if ?report_id=N or ?report-id=N is in URL
            const urlParams = new URLSearchParams(window.location.search);
            const deepLinkReportId = urlParams.get('report_id') || urlParams.get('report-id');
            if (deepLinkReportId) {
                this.currentHash = '#dashboard';
                window.location.hash = '#dashboard';
                this.fetchChartData();
                this.viewReport(parseInt(deepLinkReportId, 10));
            }

            // Debug helpers
            window._superman = this;
            window.phase1 = (ms = 2000) => this.startSupermanPhase1(ms);
            window.phase2 = (ms = 3000) => this.startSupermanPhase2(ms);
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

        // --- Copy markdown content to clipboard ---
        copyReportContent() {
            if (!this.reportModalContent) return;
            navigator.clipboard.writeText(this.reportModalContent).then(() => {
                this.reportCopied = true;
                setTimeout(() => { this.reportCopied = false; }, 2000);
            });
        },

        // --- Copy shareable URL (with report_id param) to clipboard ---
        shareReport() {
            if (!this.reportModalMeta) return;
            const url = new URL(window.location.href);
            url.searchParams.set('report_id', this.reportModalMeta.id);
            url.hash = '#dashboard';
            const shareUrl = url.toString();
            history.replaceState(null, '', shareUrl);
            navigator.clipboard.writeText(shareUrl).then(() => {
                this.reportShared = true;
                setTimeout(() => { this.reportShared = false; }, 2000);
            });
        },

        // --- Close report modal and clean up URL param ---
        closeReportModal() {
            this.reportModalOpen = false;
            const url = new URL(window.location.href);
            let changed = false;
            if (url.searchParams.has('report_id')) { url.searchParams.delete('report_id'); changed = true; }
            if (url.searchParams.has('report-id')) { url.searchParams.delete('report-id'); changed = true; }
            if (changed) history.replaceState(null, '', url.toString());
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
            if (jobType === 'jira') {
                await this.triggerSupermanSequence();
                return;
            }
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

        // --- Configure marked custom renderers (called once at init) ---
        initMarkdown() {
            if (typeof marked === 'undefined') return;
            const self = this;
            window.openImagePreview = function(src) {
                self.imgLightboxSrc = src;
                self.imgLightboxScale = 1;
                self.imgLightboxNaturalW = 0;
                self.imgLightboxOpen = true;
            };
            // Only override link and image — table scroll wrapper is applied in
            // renderMarkdown() via string post-processing to avoid the marked v12
            // Renderer.tablecell parser-context issue that caused silent failures.
            marked.use({
                renderer: {
                    link({ href, title, text }) {
                        const t = title ? ` title="${title}"` : '';
                        return `<a href="${href}"${t} target="_blank" rel="noopener noreferrer">${text}</a>`;
                    },
                    image({ href, title, text }) {
                        const t = title ? ` title="${title}"` : '';
                        return `<img src="${href}" alt="${text}"${t} class="md-img-clickable" onclick="window.openImagePreview(this.src)">`;
                    }
                }
            });
        },

        // --- Image Lightbox Controls ---
        openImgLightbox(src) {
            this.imgLightboxSrc = src;
            this.imgLightboxScale = 1;
            this.imgLightboxNaturalW = 0;
            this.imgLightboxOpen = true;
        },
        closeImgLightbox() {
            this.imgLightboxOpen = false;
        },
        zoomInImg() {
            this.imgLightboxScale = Math.min(+(this.imgLightboxScale + 0.25).toFixed(2), 5);
        },
        zoomOutImg() {
            this.imgLightboxScale = Math.max(+(this.imgLightboxScale - 0.25).toFixed(2), 0.25);
        },

        // --- Render Markdown to HTML using marked.js ---
        renderMarkdown(content) {
            if (!content) return '';
            if (typeof marked === 'undefined') return this.escapeHtml(content);
            try {
                const html = marked.parse(content);
                // Wrap tables for horizontal scroll via post-processing.
                // Avoids a custom table renderer in marked.use() which requires
                // tablecell/tablerow to have a live parser context attached.
                return html
                    .replace(/<table>/g, '<div style="width:100%;overflow-x:auto;"><table>')
                    .replace(/<\/table>/g, '</table></div>');
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
                            // 0px for scale/axis tick labels (drawn during this phase)
                            if (chart.ctx && 'letterSpacing' in chart.ctx) {
                                chart.ctx.letterSpacing = '0px';
                            }
                        },
                        beforeDatasetsDraw(chart) {
                            // Restore wide spacing for datasets and legend
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
                                bodyFont: { family: 'Share Tech Mono', size: 12 },
                                borderColor: '#334155',
                                borderWidth: 1,
                                padding: { left: 14, right: 14, top: 10, bottom: 10 }
                            }
                        },
                        scales: {
                            x: {
                                grid: { color: 'rgba(51, 65, 85, 0.15)' },
                                ticks: {
                                    color: '#94a3b8',
                                    font: { family: 'Share Tech Mono', size: 11 },
                                    maxRotation: 45,
                                    minRotation: 45,
                                    autoSkip: true,
                                    maxTicksLimit: 15
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
        },

        // ================================================================
        // SUPERMAN JIRA EASTER EGG — Revised full animation sequence
        // ================================================================

        async triggerSupermanSequence() {
            if (this.supermanRunning) return;
            this.supermanRunning = true;

            // 1 second per number, MAX_COUNT→1 countdown
            const MAX_COUNT = 8;
            const STEP_MS = 1000;

            this.appendLog('[DANGEROUS]: COUNT DOWN TO DESTROY WORLD.');
            this.triggerScreenShake();

            // Wait for shake animation to finish (1400ms) before showing countdown
            await new Promise(r => setTimeout(r, 1400));

            const overlay = document.getElementById('superman-countdown-overlay');
            const canvas  = document.getElementById('superman-countdown-canvas');
            canvas.width        = window.innerWidth;
            canvas.height       = window.innerHeight;
            canvas.style.width  = canvas.width  + 'px';
            canvas.style.height = canvas.height + 'px';
            overlay.style.display = 'block';

            // Schedule Superman phases concurrently with countdown
            // Phase 1 starts when countdown reaches 5 (= after MAX_COUNT-5 steps)
            const p1Delay  = (MAX_COUNT - 5) * STEP_MS;  // 3000ms
            const p2Delay  = (MAX_COUNT - 3) * STEP_MS;  // 5000ms
            const p1Dur    = p2Delay - p1Delay; // 2000ms
            const p2Dur    = MAX_COUNT * STEP_MS - p2Delay - 500; // 2500ms

            const t1 = setTimeout(() => {
                this.appendLog('[BREACH]: SUPERMAN DETECTED — PHASE 1 (TOP-LEFT → MID-RIGHT).');
                this.startSupermanPhase1(p1Dur);
            }, p1Delay);

            const t2 = setTimeout(() => {
                this.appendLog('[BREACH]: SUPERMAN PHASE 2 — APPROACHING SCREEN. STAND BY.');
                this.startSupermanPhase2(p2Dur);
            }, p2Delay);


            // Run countdown 10 → 1 (each number takes STEP_MS)
            for (let i = MAX_COUNT; i >= 1; i--) {
                this.appendLog(`[WARNING]: DESTROY IN ${i}...`);
                if (i === 2) this.triggerScreenCrash();
                await this.animateCountdownNumber(i, STEP_MS);
            }

            clearTimeout(t1);
            clearTimeout(t2);

            

            await new Promise(r => setTimeout(r, 600));
            overlay.style.display = 'none';

            const figure = document.getElementById('superman-flying-figure');
            figure.style.display    = 'none';
            figure.style.transition = 'none';

            // Phase 3: Superman rises slowly from below, hovers, speech bubble
            await new Promise(r => setTimeout(r, 380));
            await this.showRisingSuperman();
        },

        animateCountdownNumber(n, stepMs) {
            return new Promise(resolve => {
                const canvas = document.getElementById('superman-countdown-canvas');
                // Sync pixel dimensions with CSS display size to prevent squish bug
                canvas.width        = window.innerWidth;
                canvas.height       = window.innerHeight;
                canvas.style.width  = canvas.width  + 'px';
                canvas.style.height = canvas.height + 'px';
                const ctx      = canvas.getContext('2d');
                const cx       = canvas.width  / 2;
                const cy       = canvas.height / 2;
                const duration = stepMs;
                let start = null;

                const draw = (ts) => {
                    if (!start) start = ts;
                    const p = Math.min((ts - start) / duration, 1);

                    // Scale: burst in large → settle to 1 → slight shrink at end
                    const scale = p < 0.14
                        ? 1.75 - (0.75 * p / 0.14)
                        : p < 0.80
                            ? 1.0
                            : 1.0 - 0.12 * ((p - 0.80) / 0.20);

                    // Opacity: quick fade-in → hold → quick fade-out
                    const alpha = p < 0.07
                        ? p / 0.07
                        : p > 0.90
                            ? 1 - (p - 0.90) / 0.10
                            : 1;

                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    ctx.save();
                    ctx.globalAlpha = alpha;
                    ctx.translate(cx, cy);
                    ctx.scale(scale, scale);

                    // Outer glow ring
                    ctx.beginPath();
                    ctx.arc(0, 0, 160, 0, Math.PI * 2);
                    ctx.strokeStyle = 'rgba(239,68,68,0.42)';
                    ctx.lineWidth = 3;
                    ctx.shadowColor = 'rgba(239,68,68,0.8)';
                    ctx.shadowBlur = 28;
                    ctx.stroke();

                    // Inner ring
                    ctx.beginPath();
                    ctx.arc(0, 0, 132, 0, Math.PI * 2);
                    ctx.strokeStyle = 'rgba(239,68,68,0.18)';
                    ctx.lineWidth = 1.5;
                    ctx.shadowBlur = 0;
                    ctx.stroke();

                    // Big number (only the number animates — title is static HTML)
                    ctx.shadowColor = 'rgba(239,68,68,0.98)';
                    ctx.shadowBlur = 65;
                    ctx.font = 'bold 260px Orbitron, monospace';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.fillStyle = '#ef4444';
                    ctx.fillText(String(n), 0, 0);

                    ctx.restore();

                    if (p < 1) requestAnimationFrame(draw);
                    else resolve();
                };
                requestAnimationFrame(draw);
            });
        },

        startSupermanPhase1(durationMs) {
            const figure = document.getElementById('superman-flying-figure');
            figure.style.display    = 'block';
            figure.style.transition = 'none';
            // Start: off-screen top-left, small
            figure.style.transform  = 'translate(-300px, 5px) scale(0.5) rotate(-22deg)';
            void figure.offsetWidth;
            // Fly off-screen to the right
            figure.style.transition = `transform ${durationMs}ms ease-in`;
            figure.style.transform  = 'translate(120vw, 10vh) scale(1) rotate(-8deg)';
        },

        startSupermanPhase2(durationMs) {
            const figure = document.getElementById('superman-flying-figure');
            // Instantly flip to face left at same right-side position
            figure.style.transition = 'none';
            figure.style.transform  = 'translate(110vw, 8vh) scale(1) scaleX(-1) rotate(22deg)';
            void figure.offsetWidth;
            // Fly off-screen to the left
            figure.style.transition = `transform ${durationMs}ms ease-in`;
            figure.style.transform  = 'translate(-30vw, calc(50vh + 120px)) scale(3.6) scaleX(-1) rotate(30deg)';
        },

        async triggerScreenCrash() {
            const flash = document.getElementById('superman-impact-flash');
            const crack = document.getElementById('superman-crack-overlay');

            flash.style.display = 'block';
            flash.classList.remove('impact-flash');
            void flash.offsetWidth;
            flash.classList.add('impact-flash');

            crack.style.display = 'block';
            crack.classList.remove('crack-appear');
            void crack.offsetWidth;
            crack.classList.add('crack-appear');

            document.body.classList.add('shake-heavy');
            this.appendLog('[IMPACT]: ████ SCREEN BREACH CONFIRMED ████ STRUCTURAL DAMAGE: CRITICAL');

            await new Promise(r => setTimeout(r, 300));
            document.body.classList.remove('shake-heavy');

            flash.style.display = 'none';
            flash.classList.remove('impact-flash');
        },

        async showRisingSuperman() {
            const wrapper    = document.getElementById('superman-rise-wrapper');
            const figure     = document.getElementById('superman-standing-figure');
            const bubble     = document.getElementById('superman-speech-bubble');
            const banner     = document.getElementById('arrested-banner');
            const dismissBtn = document.getElementById('superman-dismiss-btn');

            // Start below screen, then rise slowly to mid-air
            wrapper.style.transition = 'none';
            wrapper.style.transform  = 'translateY(420px)';
            wrapper.style.display    = 'block';
            void wrapper.offsetWidth;

            wrapper.style.transition = 'transform 2.8s cubic-bezier(0.22, 1, 0.36, 1)';
            wrapper.style.transform  = 'translateY(-10vh)';
            this.appendLog('[SUPERMAN]: ASCENDING — JUSTICE WILL BE SERVED.');

            // Wait for rise to complete, then start floating
            await new Promise(r => setTimeout(r, 2300));
            figure.classList.add('superman-hover');

            // Speech bubble pops in
            bubble.style.display = 'block';
            bubble.classList.remove('bubble-pop');
            void bubble.offsetWidth;
            bubble.classList.add('bubble-pop');
            this.appendLog('[SUPERMAN]: "In the name of Truth and Justice, YOU ARE ARRESTED!"');

            // Arrested banner drops from top
            await new Promise(r => setTimeout(r, 500));
            banner.style.display = 'block';
            banner.classList.remove('arrested-drop');
            void banner.offsetWidth;
            banner.classList.add('arrested-drop');
            this.appendLog('[SYSTEM]: SENTENCE DELIVERED.');

            // Dismiss button
            setTimeout(() => { dismissBtn.style.display = 'block'; }, 1400);
        },

        dismissSupermanScene() {
            const wrapper    = document.getElementById('superman-rise-wrapper');
            const figure     = document.getElementById('superman-standing-figure');
            const flyFigure  = document.getElementById('superman-flying-figure');
            const bubble     = document.getElementById('superman-speech-bubble');
            const banner     = document.getElementById('arrested-banner');
            const crack      = document.getElementById('superman-crack-overlay');
            const dismissBtn = document.getElementById('superman-dismiss-btn');
            const overlay    = document.getElementById('superman-countdown-overlay');

            wrapper.style.display    = 'none';
            wrapper.style.transform  = '';
            wrapper.style.transition = '';
            flyFigure.style.display  = 'none';
            flyFigure.style.transform  = '';
            flyFigure.style.transition = '';
            bubble.style.display     = 'none';
            banner.style.display     = 'none';
            crack.style.display      = 'none';
            dismissBtn.style.display = 'none';
            overlay.style.display    = 'none';

            figure.classList.remove('superman-hover');
            bubble.classList.remove('bubble-pop');
            banner.classList.remove('arrested-drop');
            crack.classList.remove('crack-appear');

            document.body.classList.remove('shake-effect', 'shake-heavy');
            this.glassOpenA      = false;
            this.supermanRunning = false;
            this.appendLog('[SYSTEM]: Scene dismissed. Trật tự đã được khôi phục. Lồng bảo vệ sự sống đã đóng lại.');
        },
    }
}
