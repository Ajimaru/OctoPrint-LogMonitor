/**
 * OctoPrint Log Monitor Plugin
 * JavaScript ViewModel
 */

$(function () {
    function LogmonitorViewModel(parameters) {
        var self = this;
        // BlueprintPlugin routes are served under /plugin/<id>/, NOT /api/plugin/<id>/
        var pluginBaseUrl = "/plugin/logmonitor";

        function pluginAjax(opts) {
            return $.ajax(opts);
        }

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

            var body = { message: String(message || "") };
            if (typeof payload !== "undefined") {
                body.payload = payload;
            }

            pluginAjax({
                url: pluginBaseUrl + "/debug/frontend",
                method: "POST",
                data: JSON.stringify(body),
                contentType: "application/json",
                dataType: "json",
            }).fail(function () {
                // Intentionally silent: never spam browser console for debug logging.
            });
        };

        // Line buffer for batching DOM updates
        var lineBuffer = [];
        var flushIntervalId = null;

        function flushLineBuffer() {
            if (lineBuffer.length === 0) return;
            var batch = lineBuffer.splice(0, lineBuffer.length);
            var maxLines = getPluginSetting("max_stream_lines", 500);
            var combined = self.allLines().concat(batch);
            if (combined.length > maxLines) {
                combined = combined.slice(combined.length - maxLines);
            }
            self.allLines(combined);
            if (self.autoScroll()) {
                self.scrollToBottom();
            }
        }

        // Observable: Stream state
        self.isStreaming = ko.observable(false);
        self.isSwitchingStream = ko.observable(false);
        self.selectedLogFile = ko.observable("");
        self.activeStreamFile = ko.observable("");
        self.availableLogFiles = ko.observableArray([]);
        self.allLines = ko.observableArray([]);
        var suppressStreamSwitch = false;

        function setSelectedLogFile(value) {
            suppressStreamSwitch = true;
            self.selectedLogFile(value);
            suppressStreamSwitch = false;
        }

        self.lineCount = ko.computed(function () {
            return self.allLines().length;
        });

        // Observable: Filters
        self.autoScroll = ko.observable(true);
        self.filterText = ko.observable("");
        self.showDebug = ko.observable(false);
        self.showInfo = ko.observable(false);
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
                var activeFile =
                    self.activeStreamFile() || self.selectedLogFile();
                var text = "Streaming: " + activeFile;
                if (self.isSwitchingStream()) {
                    text += " (switching...)";
                }
                return text;
            }
            return "Not streaming";
        });

        // Computed: Stream button text
        self.streamButtonText = ko.computed(function () {
            return self.isStreaming() ? "Stop Streaming" : "Start Streaming";
        });

        self.streamControlsDisabled = ko.pureComputed(function () {
            return self.isSwitchingStream();
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

        self.updateSettingsDefaultLogFileDropdown = function (fileNames) {
            var select = $("#settings_plugin_logmonitor_default_log_file");
            if (!select.length) return;

            var current = getPluginSetting("default_log_file", "");

            select.empty();
            select.append($('<option value="">Select log file...</option>'));

            fileNames.forEach(function (name) {
                select.append($("<option></option>").val(name).text(name));
            });

            if (current && fileNames.indexOf(current) !== -1) {
                select.val(current);
            }
        };

        self.updateSettingsAlertMonitoredLogsDropdown = function (fileNames) {
            var select = $("#settings_plugin_logmonitor_alerts_monitored_logs");
            if (!select.length) return;

            var current = getPluginSetting("alerts_monitored_logs", []);
            var selected = Array.isArray(current)
                ? current
                : typeof current === "string" && current
                  ? [current]
                  : [];

            select.empty();

            fileNames.forEach(function (name) {
                var option = $("<option></option>").val(name).text(name);
                if (selected.indexOf(name) !== -1) {
                    option.prop("selected", true);
                }
                select.append(option);
            });
        };

        self.renderAlertMonitorStatus = function (data, errorText) {
            var target = $("#settings_plugin_logmonitor_alert_monitor_status");
            var badge = $(
                "#settings_plugin_logmonitor_alert_monitor_status_badge",
            );
            if (!target.length) return;

            if (errorText) {
                target.text("Failed to load status: " + errorText);
                if (badge.length) {
                    badge
                        .text("Error")
                        .removeClass("badge-success badge-warning badge-info")
                        .addClass("badge-important");
                }
                return;
            }

            var mode = (data && data.mode) || "unknown";
            var activeLogs = Array.isArray(data && data.active_logs)
                ? data.active_logs
                : [];
            var configuredLogs = Array.isArray(data && data.configured_logs)
                ? data.configured_logs
                : [];

            var activeText =
                activeLogs.length > 0 ? activeLogs.join(", ") : "none";
            var configuredText =
                configuredLogs.length > 0 ? configuredLogs.join(", ") : "none";

            if (badge.length) {
                if (activeLogs.length > 0) {
                    badge
                        .text("Active")
                        .removeClass("badge-warning badge-info badge-important")
                        .addClass("badge-success");
                } else {
                    badge
                        .text("Idle")
                        .removeClass("badge-success badge-info badge-important")
                        .addClass("badge-warning");
                }
            }

            target.text(
                "Mode: " +
                    mode +
                    " | Active: " +
                    activeText +
                    " | Configured: " +
                    configuredText,
            );
        };

        self.loadAlertMonitorStatus = function () {
            var target = $("#settings_plugin_logmonitor_alert_monitor_status");
            var badge = $(
                "#settings_plugin_logmonitor_alert_monitor_status_badge",
            );
            if (target.length) {
                target.text("Loading alert monitor status...");
            }
            if (badge.length) {
                badge
                    .text("Loading")
                    .removeClass("badge-success badge-warning badge-important")
                    .addClass("badge-info");
            }

            pluginAjax({
                url: pluginBaseUrl + "/alerts/monitor/status",
                method: "GET",
                dataType: "json",
            })
                .done(function (response) {
                    self.renderAlertMonitorStatus(response);
                })
                .fail(function (xhr) {
                    self.renderAlertMonitorStatus(
                        null,
                        (xhr && xhr.statusText) || "request failed",
                    );
                });
        };

        function selectPreferredLogFile(fileNames) {
            if (!Array.isArray(fileNames) || fileNames.length === 0) return;

            var defaultFile = getPluginSetting("default_log_file", "");
            var currentSelection = self.selectedLogFile();

            if (defaultFile && fileNames.indexOf(defaultFile) !== -1) {
                setSelectedLogFile(defaultFile);
                return;
            }

            if (
                currentSelection &&
                fileNames.indexOf(currentSelection) !== -1
            ) {
                return;
            }

            setSelectedLogFile(fileNames[0]);
        }

        // Initialize
        self.onBeforeBinding = function () {
            self.autoScroll(!!getPluginSetting("auto_scroll", true));
            self.loadAvailableFiles();
        };

        // Load available log files
        self.loadAvailableFiles = function () {
            pluginAjax({
                url: pluginBaseUrl + "/files",
                method: "GET",
                dataType: "json",
            })
                .done(function (response) {
                    var rawFiles = Array.isArray(response && response.files)
                        ? response.files
                        : [];

                    var fileNames = rawFiles
                        .map(function (file) {
                            return typeof file === "string"
                                ? file
                                : file && file.name;
                        })
                        .filter(function (name) {
                            return typeof name === "string" && name.length > 0;
                        });

                    self.availableLogFiles(fileNames);
                    self.updateSettingsDefaultLogFileDropdown(fileNames);
                    self.updateSettingsAlertMonitoredLogsDropdown(fileNames);
                    selectPreferredLogFile(fileNames);
                })
                .fail(function (xhr) {
                    self.debugLog("Failed to load log file list", {
                        status: xhr && xhr.status,
                        responseText: xhr && xhr.responseText,
                        url: pluginBaseUrl + "/files",
                    });
                    new PNotify({
                        title: "Log Monitor",
                        text: "Could not load available log files.",
                        type: "error",
                    });
                });
        };

        self.onSettingsShown = function () {
            var files = self.availableLogFiles();
            if (files.length > 0) {
                self.updateSettingsDefaultLogFileDropdown(files);
                self.updateSettingsAlertMonitoredLogsDropdown(files);
            } else {
                self.loadAvailableFiles();
            }

            $("#settings_plugin_logmonitor_alert_monitor_refresh")
                .off("click.logmonitor")
                .on("click.logmonitor", function () {
                    self.loadAlertMonitorStatus();
                });

            self.loadAlertMonitorStatus();
        };

        self.onEventSettingsUpdated = function () {
            // Backend alert monitor gets restarted after settings save; refresh shown status.
            self.loadAlertMonitorStatus();
        };

        // Stream control
        self.toggleStream = function () {
            if (self.isSwitchingStream()) return;

            if (self.isStreaming()) {
                self.stopStream();
            } else {
                self.startStream();
            }
        };

        self.startStream = function (targetFile, options) {
            var opts = options || {};
            var streamFile = targetFile || self.selectedLogFile();
            if (!streamFile) {
                new PNotify({
                    title: "Log Monitor",
                    text: "Please select a log file first",
                    type: "error",
                });
                return;
            }

            if (self.isSwitchingStream()) return;
            self.isSwitchingStream(true);

            pluginAjax({
                url: pluginBaseUrl + "/stream/start",
                method: "POST",
                data: JSON.stringify({ file: streamFile }),
                contentType: "application/json",
                dataType: "json",
            })
                .done(function (response) {
                    if (opts.isAutoSwitch) {
                        lineBuffer.length = 0;
                        self.allLines([]);
                    }

                    self.isStreaming(true);
                    self.activeStreamFile(
                        (response && response.file) || streamFile,
                    );

                    if (!flushIntervalId) {
                        flushIntervalId = setInterval(flushLineBuffer, 1000);
                    }

                    // Show initial lines if available
                    if (response.initial_lines) {
                        response.initial_lines.forEach(function (line) {
                            lineBuffer.push(line);
                        });
                    }
                })
                .fail(function (error) {
                    if (opts.isAutoSwitch) {
                        setSelectedLogFile(self.activeStreamFile() || "");
                    }
                    new PNotify({
                        title: "Stream Error",
                        text: "Failed to start streaming",
                        type: "error",
                    });
                })
                .always(function () {
                    self.isSwitchingStream(false);
                });
        };

        self.stopStream = function () {
            pluginAjax({
                url: pluginBaseUrl + "/stream/stop",
                method: "POST",
                contentType: "application/json",
                dataType: "json",
            })
                .done(function () {
                    clearInterval(flushIntervalId);
                    flushIntervalId = null;
                    flushLineBuffer();
                    self.isStreaming(false);
                    self.activeStreamFile("");
                })
                .fail(function (error) {
                    new PNotify({
                        title: "Stream Error",
                        text: "Failed to stop streaming",
                        type: "error",
                    });
                })
                .always(function () {
                    self.isSwitchingStream(false);
                });
        };

        self.clearDisplay = function () {
            lineBuffer.length = 0;
            self.allLines([]);
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

            pluginAjax({
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
                    self.debugLog("Search failed", {
                        status: error && error.status,
                        responseText: error && error.responseText,
                    });
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
            pluginAjax({
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

            pluginAjax({
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
            pluginAjax({
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

            pluginAjax({
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
        };

        self.onAfterBinding = function () {
            bindVisibilityToSetting("show_navbar", self.showNavbar);
            bindVisibilityToSetting("show_sidebar", self.showSidebar);

            var pluginSettings = getPluginSettings();
            var defaultLogFileObs =
                pluginSettings && pluginSettings.default_log_file;
            if (typeof defaultLogFileObs === "function") {
                defaultLogFileObs.subscribe(function (newValue) {
                    var files = self.availableLogFiles();
                    if (
                        !self.isStreaming() &&
                        typeof newValue === "string" &&
                        files.indexOf(newValue) !== -1
                    ) {
                        setSelectedLogFile(newValue);
                    }
                });
            }

            self.selectedLogFile.subscribe(function (newValue) {
                if (suppressStreamSwitch) return;
                if (!self.isStreaming() || self.isSwitchingStream()) return;
                if (typeof newValue !== "string" || newValue.length === 0)
                    return;
                if (newValue === self.activeStreamFile()) return;

                self.startStream(newValue, { isAutoSwitch: true });
            });

            if (
                self.settings.settings.plugins.logmonitor.auto_start_streaming()
            ) {
                var file =
                    self.settings.settings.plugins.logmonitor.default_log_file();
                if (file) {
                    setSelectedLogFile(file);
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
                lineBuffer.push(data.data);
            } else if (data.type === "log_lines") {
                if (Array.isArray(data.data)) {
                    data.data.forEach(function (line) {
                        lineBuffer.push(line);
                    });
                }
            } else if (data.type === "severity_alert") {
                self.handleAlert(data);
            }
        };

        self.handleLogLine = function (line) {
            lineBuffer.push(line);
        };

        self.handleAlert = function (alert) {
            self.alertCount(alert.count);
            self.alertLevel(alert.level);

            // In-app OctoPrint-style toast notification (PNotify)
            if (alert.notification_enabled) {
                var notificationMessage =
                    alert.message || "Severity: " + alert.level;
                var pnotifyType = "info";

                if (alert.level === "CRITICAL" || alert.level === "ERROR") {
                    pnotifyType = "error";
                } else if (alert.level === "WARNING") {
                    pnotifyType = "notice";
                }

                new PNotify({
                    title: "Log Monitor - " + alert.level,
                    text: notificationMessage,
                    type: pnotifyType,
                });
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
