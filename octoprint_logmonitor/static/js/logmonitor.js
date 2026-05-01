/**
 * OctoPrint Log Monitor Plugin
 * JavaScript ViewModel
 */

$(function () {
    function LogmonitorViewModel(parameters) {
        var self = this;
        var pluginBaseUrl = API_BASEURL + "plugin/logmonitor";

        self.settings = parameters[0];
        self.loginState = parameters[1];

        function getPluginSettings() {
            var root = self.settings && self.settings.settings;
            return root && root.plugins ? root.plugins.logmonitor : null;
        }

        function getPluginSetting(settingName, fallbackValue) {
            var ps = getPluginSettings();
            var setting = ps && ps[settingName];
            if (typeof setting === "function") return setting();
            return setting === undefined || setting === null
                ? fallbackValue
                : setting;
        }

        self.isDebugMode = ko.pureComputed(function () {
            return !!getPluginSetting("debug_mode", false);
        });

        self.debugLog = function (message, payload) {
            if (!self.isDebugMode()) return;
            if (typeof payload === "undefined") {
                console.log("[LogMonitor Debug] " + message);
            } else {
                console.log("[LogMonitor Debug] " + message, payload);
            }
        };

        // Observable: Stream state
        self.isStreaming = ko.observable(false);
        self.selectedLogFile = ko.observable("");
        self.availableLogFiles = ko.observableArray([]);
        self.allLines = ko.observableArray([]);
        self.lineCount = ko.computed(function () {
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
        self.hasAlerts = ko.computed(function () {
            return self.alertCount() > 0;
        });
        self.alertText = ko.computed(function () {
            return self.alertLevel() + ": " + self.alertCount();
        });
        self.alertClass = ko.computed(function () {
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
        self.displayedLines = ko.computed(function () {
            var lines = self.allLines();
            var filter = self.filterText().toLowerCase();

            return lines.filter(function (line) {
                // Apply severity filter
                if (line.level === "DEBUG" && !self.showDebug()) return false;
                if (line.level === "INFO" && !self.showInfo()) return false;
                if (line.level === "WARNING" && !self.showWarning())
                    return false;
                if (line.level === "ERROR" && !self.showError()) return false;
                if (line.level === "CRITICAL" && !self.showCritical())
                    return false;

                // Apply text filter
                if (
                    filter &&
                    line.message.toLowerCase().indexOf(filter) === -1
                ) {
                    return false;
                }

                return true;
            });
        });

        // Computed: Status text
        self.statusText = ko.computed(function () {
            if (self.isStreaming()) {
                return "Streaming: " + self.selectedLogFile();
            }
            return "Not streaming";
        });

        // Computed: Stream button text
        self.streamButtonText = ko.computed(function () {
            return self.isStreaming() ? "Stop Streaming" : "Start Streaming";
        });

        // Computed: Sidebar status
        self.statusIcon = ko.computed(function () {
            if (self.hasAlerts()) {
                return "fa-exclamation-triangle text-error";
            }
            return "fa-check text-success";
        });

        self.statusSummary = ko.computed(function () {
            if (self.hasAlerts()) {
                return (
                    self.alertCount() + " " + self.alertLevel() + " alert(s)"
                );
            }
            return "No alerts";
        });

        self.showNavbar = ko.observable(
            !!getPluginSetting("show_navbar", true),
        );
        self.showSidebar = ko.observable(
            !!getPluginSetting("show_sidebar", true),
        );

        function bindVisibilityToSetting(settingKey, target) {
            var ps = getPluginSettings();
            var obs = ps && ps[settingKey];
            if (typeof obs !== "function") return;
            target(!!obs());
            obs.subscribe(function (v) {
                target(!!v);
            });
        }

        // Computed: Pagination
        self.canGoPrevious = ko.computed(function () {
            return self.currentPage() > 0;
        });

        self.canGoNext = ko.pureComputed(function () {
            var pageSize = getPluginSetting("search_page_size", 50);
            return (self.currentPage() + 1) * pageSize < self.totalResults();
        });

        self.paginationInfo = ko.pureComputed(function () {
            var pageSize = getPluginSetting("search_page_size", 50);
            var start = self.currentPage() * pageSize + 1;
            var end = Math.min(
                (self.currentPage() + 1) * pageSize,
                self.totalResults(),
            );
            return (
                "Showing " + start + "-" + end + " of " + self.totalResults()
            );
        });

        // Initialize
        self.onBeforeBinding = function () {
            self.autoScroll(!!getPluginSetting("auto_scroll", true));
            self.loadAvailableFiles();
        };

        // Load available log files
        self.loadAvailableFiles = function () {
            $.ajax({
                url: pluginBaseUrl + "/files",
                method: "GET",
                dataType: "json",
            }).done(function (response) {
                if (response.files) {
                    self.availableLogFiles(
                        response.files.map(function (file) {
                            return file.name;
                        }),
                    );
                    if (response.files.length > 0) {
                        var defaultFile =
                            self.settings.settings.plugins.logmonitor.default_log_file();
                        if (
                            response.files.some(function (file) {
                                return file.name === defaultFile;
                            })
                        ) {
                            self.selectedLogFile(defaultFile);
                        } else {
                            self.selectedLogFile(response.files[0].name);
                        }
                    }
                }
            });
        };

        // Stream control
        self.toggleStream = function () {
            if (self.isStreaming()) {
                self.stopStream();
            } else {
                self.startStream();
            }
        };

        self.startStream = function () {
            if (!self.selectedLogFile()) {
                new PNotify({
                    title: "Log Monitor",
                    text: "Please select a log file first",
                    type: "error",
                });
                return;
            }

            $.ajax({
                url: pluginBaseUrl + "/stream/start",
                method: "POST",
                data: JSON.stringify({ file: self.selectedLogFile() }),
                contentType: "application/json",
                dataType: "json",
            })
                .done(function (response) {
                    self.isStreaming(true);
                    // Show initial lines if available
                    if (response.initial_lines) {
                        response.initial_lines.forEach(function (line) {
                            self.handleLogLine(line);
                        });
                    }
                })
                .fail(function (error) {
                    new PNotify({
                        title: "Stream Error",
                        text: "Failed to start streaming",
                        type: "error",
                    });
                });
        };

        self.stopStream = function () {
            $.ajax({
                url: pluginBaseUrl + "/stream/stop",
                method: "POST",
                contentType: "application/json",
                dataType: "json",
            })
                .done(function () {
                    self.isStreaming(false);
                })
                .fail(function (error) {
                    new PNotify({
                        title: "Stream Error",
                        text: "Failed to stop streaming",
                        type: "error",
                    });
                });
        };

        self.clearDisplay = function () {
            self.allLines.removeAll();
        };

        // Search functions
        self.performSearch = function () {
            var levels = [];
            if (self.searchDebug()) levels.push("DEBUG");
            if (self.searchInfo()) levels.push("INFO");
            if (self.searchWarning()) levels.push("WARNING");
            if (self.searchError()) levels.push("ERROR");
            if (self.searchCritical()) levels.push("CRITICAL");

            var pageSize =
                self.settings.settings.plugins.logmonitor.search_page_size();
            var offset = self.currentPage() * pageSize;

            $.ajax({
                url: pluginBaseUrl + "/search",
                method: "GET",
                dataType: "json",
                traditional: true,
                data: {
                    file: self.selectedLogFile(),
                    query: self.searchQuery(),
                    levels: levels,
                    offset: offset,
                    limit: pageSize,
                    case_sensitive: self.caseSensitive(),
                    use_regex: self.useRegex(),
                },
            })
                .done(function (response) {
                    self.searchResults(response.results);
                    self.totalResults(response.total);
                    self.hasSearched(true);
                })
                .fail(function (error) {
                    console.error("Search failed:", error);
                    new PNotify({
                        title: "Search Failed",
                        text: "Error performing search",
                        type: "error",
                    });
                });
        };

        self.previousPage = function () {
            if (self.canGoPrevious()) {
                self.currentPage(self.currentPage() - 1);
                self.performSearch();
            }
        };

        self.nextPage = function () {
            if (self.canGoNext()) {
                self.currentPage(self.currentPage() + 1);
                self.performSearch();
            }
        };

        // Alert functions
        self.resetAlerts = function () {
            $.ajax({
                url: pluginBaseUrl + "/alerts/reset",
                method: "POST",
                contentType: "application/json",
                dataType: "json",
            }).done(function () {
                self.alertCount(0);
                self.alertLevel("");
            });
        };

        // NEW: Export functions
        self.exportResults = function (format) {
            if (self.searchResults().length === 0) {
                alert("No results to export");
                return;
            }

            var safeFormat = format === "txt" ? "txt" : "csv";

            $.ajax({
                url: pluginBaseUrl + "/export",
                method: "POST",
                data: JSON.stringify({
                    results: self.searchResults(),
                    format: safeFormat,
                }),
                contentType: "application/json",
                dataType: "text",
                success: function (data) {
                    var blob = new Blob([data], { type: "text/plain" });
                    var url = window.URL.createObjectURL(blob);
                    var link = document.createElement("a");
                    link.href = url;
                    link.download = "logmonitor_export." + safeFormat;
                    link.rel = "noopener";
                    link.click();
                    window.URL.revokeObjectURL(url);
                },
                error: function () {
                    alert("Failed to export results");
                },
            });
        };

        // NEW: Download log file
        self.downloadLogFile = function (filename) {
            var url =
                pluginBaseUrl + "/download/" + encodeURIComponent(filename);
            window.location.href = url;
        };

        // NEW: Load alert history
        self.loadAlertHistory = function () {
            $.ajax({
                url: pluginBaseUrl + "/alert-history",
                method: "GET",
                dataType: "json",
            }).done(function (response) {
                self.alertHistory(response.history);
            });
        };

        // NEW: Clear alert history
        self.clearAlertHistory = function () {
            if (!confirm("Clear all alert history?")) return;

            $.ajax({
                url: pluginBaseUrl + "/alert-history/clear",
                method: "POST",
                contentType: "application/json",
                dataType: "json",
            }).done(function () {
                self.alertHistory([]);
            });
        };

        // NEW: Auto-start streaming on page load
        self.onStartup = function () {
            // Load alert history
            self.loadAlertHistory();

            // Request notification permission if enabled
            if (
                self.settings.settings.plugins.logmonitor.enable_notifications()
            ) {
                if (
                    "Notification" in window &&
                    Notification.permission === "default"
                ) {
                    Notification.requestPermission();
                }
            }
        };

        self.onAfterBinding = function () {
            bindVisibilityToSetting("show_navbar", self.showNavbar);
            bindVisibilityToSetting("show_sidebar", self.showSidebar);

            if (
                self.settings.settings.plugins.logmonitor.auto_start_streaming()
            ) {
                var file =
                    self.settings.settings.plugins.logmonitor.default_log_file();
                if (file) {
                    self.selectedLogFile(file);
                    setTimeout(function () {
                        self.startStream();
                    }, 500);
                }
            }
        };

        self.openTab = function () {
            $('a[href="#tab_plugin_logmonitor"]').tab("show");
            self.resetAlerts();
        };

        // WebSocket message handling
        self.onDataUpdaterPluginMessage = function (plugin, data) {
            if (plugin !== "logmonitor") return;

            if (data.type === "log_line") {
                self.handleLogLine(data.data);
            } else if (data.type === "severity_alert") {
                self.handleAlert(data);
            }
        };

        self.handleLogLine = function (line) {
            self.allLines.push(line);

            // Trim buffer if needed
            var maxLines =
                self.settings.settings.plugins.logmonitor.max_stream_lines();
            if (self.allLines().length > maxLines) {
                self.allLines.shift();
            }

            // Auto-scroll
            if (self.autoScroll()) {
                self.scrollToBottom();
            }
        };

        self.handleAlert = function (alert) {
            self.alertCount(alert.count);
            self.alertLevel(alert.level);

            // NEW: Browser notification support
            if (alert.notification_enabled && "Notification" in window) {
                if (Notification.permission === "granted") {
                    var notificationMessage =
                        alert.message || "Severity: " + alert.level;
                    try {
                        new Notification("Log Monitor - " + alert.level, {
                            body: notificationMessage,
                            tag: "logmonitor-alert",
                            requireInteraction: false,
                        });
                    } catch (e) {
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
                    var audio = new Audio(
                        "data:audio/wav;base64,UklGRiYAAABXQVZFZm10IBAAAAABAAEAQB8AAAB9AAACABAAZGF0YQIAAAAAAA==",
                    );
                    audio.volume = 0.5;
                    audio.play().catch(function () {
                        // Sound playback failed, continue silently
                    });
                } catch (e) {
                    // Audio not supported
                }
            }
        };

        self.scrollToBottom = function () {
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
            "#sidebar_plugin_logmonitor_wrapper",
        ],
    });
});
