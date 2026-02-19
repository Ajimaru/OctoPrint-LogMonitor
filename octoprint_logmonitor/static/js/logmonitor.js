/**
 * OctoPrint Log Monitor Plugin
 * JavaScript ViewModel
 */

$(function() {
    function LogmonitorViewModel(parameters) {
        var self = this;

        // Injected dependencies
        self.settings = parameters[0];
        self.loginState = parameters[1];

        // Observable: Stream state
        self.isStreaming = ko.observable(false);
        self.selectedLogFile = ko.observable("");
        self.availableLogFiles = ko.observableArray([]);
        self.allLines = ko.observableArray([]);
        self.lineCount = ko.computed(function() {
            return self.allLines().length;
        });

        // Observable: Filters
        self.autoScroll = ko.observable(true);
        self.filterText = ko.observable("");
        self.showDebug = ko.observable(true);
        self.showInfo = ko.observable(true);
        self.showWarning = ko.observable(true);
        self.showError = ko.observable(true);
        self.showCritical = ko.observable(true);

        // Observable: Alerts
        self.alertCount = ko.observable(0);
        self.alertLevel = ko.observable("");
        self.hasAlerts = ko.computed(function() {
            return self.alertCount() > 0;
        });
        self.alertText = ko.computed(function() {
            return self.alertLevel() + ": " + self.alertCount();
        });
        self.alertClass = ko.computed(function() {
            var level = self.alertLevel().toLowerCase();
            if (level === "critical" || level === "error") {
                return "badge-important";
            } else if (level === "warning") {
                return "badge-warning";
            }
            return "badge-info";
        });

        // Observable: Search
        self.searchQuery = ko.observable("");
        self.searchDebug = ko.observable(false);
        self.searchInfo = ko.observable(false);
        self.searchWarning = ko.observable(true);
        self.searchError = ko.observable(true);
        self.searchCritical = ko.observable(true);
        self.searchResults = ko.observableArray([]);
        self.hasSearched = ko.observable(false);
        self.currentPage = ko.observable(0);
        self.totalResults = ko.observable(0);

        // NEW: Advanced search and export features
        self.useRegex = ko.observable(false);
        self.caseSensitive = ko.observable(false);
        self.alertHistory = ko.observableArray([]);
        self.autoStartEnabled = ko.observable(false);

        // Computed: Displayed lines (filtered)
        self.displayedLines = ko.computed(function() {
            var lines = self.allLines();
            var filter = self.filterText().toLowerCase();

            return lines.filter(function(line) {
                // Apply severity filter
                if (line.level === "DEBUG" && !self.showDebug()) return false;
                if (line.level === "INFO" && !self.showInfo()) return false;
                if (line.level === "WARNING" && !self.showWarning()) return false;
                if (line.level === "ERROR" && !self.showError()) return false;
                if (line.level === "CRITICAL" && !self.showCritical()) return false;

                // Apply text filter
                if (filter && line.message.toLowerCase().indexOf(filter) === -1) {
                    return false;
                }

                return true;
            });
        });

        // Computed: Status text
        self.statusText = ko.computed(function() {
            if (self.isStreaming()) {
                return "Streaming: " + self.selectedLogFile();
            }
            return "Not streaming";
        });

        // Computed: Stream button text
        self.streamButtonText = ko.computed(function() {
            return self.isStreaming() ? "Stop Streaming" : "Start Streaming";
        });

        // Computed: Sidebar status
        self.statusIcon = ko.computed(function() {
            if (self.hasAlerts()) {
                return "fa-exclamation-triangle text-error";
            }
            return "fa-check text-success";
        });

        self.statusSummary = ko.computed(function() {
            if (self.hasAlerts()) {
                return self.alertCount() + " " + self.alertLevel() + " alert(s)";
            }
            return "No alerts";
        });

        // Computed: Pagination
        self.canGoPrevious = ko.computed(function() {
            return self.currentPage() > 0;
        });

        self.canGoNext = ko.computed(function() {
            var pageSize = self.settings.settings.plugins.logmonitor.search_page_size();
            return (self.currentPage() + 1) * pageSize < self.totalResults();
        });

        self.paginationInfo = ko.computed(function() {
            var pageSize = self.settings.settings.plugins.logmonitor.search_page_size();
            var start = self.currentPage() * pageSize + 1;
            var end = Math.min((self.currentPage() + 1) * pageSize, self.totalResults());
            return "Showing " + start + "-" + end + " of " + self.totalResults();
        });

        // Initialize
        self.onBeforeBinding = function() {
            self.autoScroll(self.settings.settings.plugins.logmonitor.auto_scroll());
            self.loadAvailableFiles();
        };

        // Load available log files
        self.loadAvailableFiles = function() {
            OctoPrint.simpleApiGet("logmonitor")
                .done(function(response) {
                    if (response.files) {
                        self.availableLogFiles(response.files);
                        if (response.files.length > 0) {
                            self.selectedLogFile(self.settings.settings.plugins.logmonitor.default_log_file());
                        }
                    }
                });
        };

        // Stream control
        self.toggleStream = function() {
            if (self.isStreaming()) {
                self.stopStream();
            } else {
                self.startStream();
            }
        };

        self.startStream = function() {
            if (!self.selectedLogFile()) {
                new PNotify({
                    title: "Log Monitor",
                    text: "Please select a log file first",
                    type: "error"
                });
                return;
            }

            OctoPrint.simpleApiCommand("logmonitor", "stream/start", {
                file: self.selectedLogFile()
            }).done(function(response) {
                self.isStreaming(true);
                // Show initial lines if available
                if (response.initial_lines) {
                    response.initial_lines.forEach(function(line) {
                        self.handleLogLine(line);
                    });
                }
            }).fail(function(error) {
                new PNotify({
                    title: "Stream Error",
                    text: "Failed to start streaming",
                    type: "error"
                });
            });
        };

        self.stopStream = function() {
            OctoPrint.simpleApiCommand("logmonitor", "stream/stop")
                .done(function() {
                    self.isStreaming(false);
                })
                .fail(function(error) {
                    new PNotify({
                        title: "Stream Error",
                        text: "Failed to stop streaming",
                        type: "error"
                    });
                });
        };

        self.clearDisplay = function() {
            self.allLines.removeAll();
        };

        // Search functions
        self.performSearch = function() {
            var levels = [];
            if (self.searchDebug()) levels.push("DEBUG");
            if (self.searchInfo()) levels.push("INFO");
            if (self.searchWarning()) levels.push("WARNING");
            if (self.searchError()) levels.push("ERROR");
            if (self.searchCritical()) levels.push("CRITICAL");

            var pageSize = self.settings.settings.plugins.logmonitor.search_page_size();
            var offset = self.currentPage() * pageSize;

            OctoPrint.simpleApiGet("logmonitor", {
                action: "search",
                file: self.selectedLogFile(),
                query: self.searchQuery(),
                levels: levels.join(","),
                offset: offset,
                limit: pageSize,
                case_sensitive: self.caseSensitive(),
                use_regex: self.useRegex()
            }).done(function(response) {
                self.searchResults(response.results);
                self.totalResults(response.total);
                self.hasSearched(true);
            }).fail(function(error) {
                console.error("Search failed:", error);
                new PNotify({
                    title: "Search Failed",
                    text: "Error performing search",
                    type: "error"
                });
            });
        };

        self.previousPage = function() {
            if (self.canGoPrevious()) {
                self.currentPage(self.currentPage() - 1);
                self.performSearch();
            }
        };

        self.nextPage = function() {
            if (self.canGoNext()) {
                self.currentPage(self.currentPage() + 1);
                self.performSearch();
            }
        };

        // Alert functions
        self.resetAlerts = function() {
            OctoPrint.simpleApiCommand("logmonitor", "alerts/reset")
                .done(function() {
                    self.alertCount(0);
                    self.alertLevel("");
                });
        };

        // NEW: Export functions
        self.exportResults = function(format) {
            if (self.searchResults().length === 0) {
                alert("No results to export");
                return;
            }

            var exportData = {
                results: self.searchResults(),
                format: format || "csv"
            };

            $.ajax({
                url: "/api/plugin/logmonitor/export",
                method: "POST",
                data: JSON.stringify(exportData),
                contentType: "application/json",
                dataType: "text",
                success: function(data) {
                    var filename = "logmonitor_export." + (format || "csv");
                    var blob = new Blob([data], {type: "text/plain"});
                    var url = window.URL.createObjectURL(blob);
                    var link = document.createElement("a");
                    link.href = url;
                    link.download = filename;
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                    window.URL.revokeObjectURL(url);
                },
                error: function() {
                    alert("Failed to export results");
                }
            });
        };

        // NEW: Download log file
        self.downloadLogFile = function(filename) {
            var url = "/api/plugin/logmonitor/download/" + filename;
            window.location.href = url;
        };

        // NEW: Load alert history
        self.loadAlertHistory = function() {
            OctoPrint.simpleApiCommand("logmonitor", "alert-history")
                .done(function(response) {
                    self.alertHistory(response.history);
                });
        };

        // NEW: Clear alert history
        self.clearAlertHistory = function() {
            if (!confirm("Clear all alert history?")) return;

            OctoPrint.simpleApiCommand("logmonitor", "alert-history/clear")
                .done(function() {
                    self.alertHistory([]);
                });
        };

        // NEW: Auto-start streaming on page load
        self.onStartup = function() {
            // Load alert history
            self.loadAlertHistory();

            // Request notification permission if enabled
            if (self.settings.settings.plugins.logmonitor.enable_notifications()) {
                if ("Notification" in window && Notification.permission === "default") {
                    Notification.requestPermission();
                }
            }
        };

        // Auto-start streaming after plugin loads
        self.onAfterBinding = function() {
            if (self.settings.settings.plugins.logmonitor.auto_start_streaming()) {
                var file = self.settings.settings.plugins.logmonitor.default_log_file();
                if (file) {
                    self.selectedLogFile(file);
                    setTimeout(function() {
                        self.startStream();
                    }, 500);
                }
            }
        };

        self.openTab = function() {
            $('a[href="#tab_plugin_logmonitor"]').tab('show');
            self.resetAlerts();
        };

        // WebSocket message handling
        self.onDataUpdaterPluginMessage = function(plugin, data) {
            if (plugin !== "logmonitor") return;

            if (data.type === "log_line") {
                self.handleLogLine(data.data);
            } else if (data.type === "severity_alert") {
                self.handleAlert(data);
            }
        };

        self.handleLogLine = function(line) {
            self.allLines.push(line);

            // Trim buffer if needed
            var maxLines = self.settings.settings.plugins.logmonitor.max_stream_lines();
            if (self.allLines().length > maxLines) {
                self.allLines.shift();
            }

            // Auto-scroll
            if (self.autoScroll()) {
                self.scrollToBottom();
            }
        };

        self.handleAlert = function(alert) {
            self.alertCount(alert.count);
            self.alertLevel(alert.level);

            // NEW: Browser notification support
            if (alert.notification_enabled && "Notification" in window) {
                if (Notification.permission === "granted") {
                    var notificationMessage = alert.message || "Severity: " + alert.level;
                    try {
                        new Notification("Log Monitor - " + alert.level, {
                            body: notificationMessage,
                            tag: "logmonitor-alert",
                            requireInteraction: false
                        });
                    } catch(e) {
                        console.error("Notification failed:", e);
                    }
                } else if (Notification.permission !== "denied") {
                    Notification.requestPermission();
                }
            }

            // NEW: Play sound if available (optional)
            if (alert.notification_enabled) {
                try {
                    // Use a small beep sound encoded in base64
                    var audio = new Audio("data:audio/wav;base64,UklGRiYAAABXQVZFZm10IBAAAAABAAEAQB8AAAB9AAACABAAZGF0YQIAAAAAAA==");
                    audio.volume = 0.5;
                    audio.play().catch(function() {
                        // Sound playback failed, continue silently
                    });
                } catch(e) {
                    // Audio not supported
                }
            }
        };

        self.scrollToBottom = function() {
            var container = $(".logmonitor-output");
            if (container.length) {
                container.scrollTop(container[0].scrollHeight);
            }
        };
    }

    // Register ViewModel
    OCTOPRINT_VIEWMODELS.push({
        construct: LogmonitorViewModel,
        dependencies: ["settingsViewModel", "loginStateViewModel"],
        elements: [
            "#tab_plugin_logmonitor",
            "#navbar_plugin_logmonitor",
            "#sidebar_plugin_logmonitor"
        ]
    });
});
