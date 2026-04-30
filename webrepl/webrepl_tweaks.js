// Set terminal height dynamically, without modifying webrepl.js
(function() {
    var maxReadyAttempts = 60;
    var readyAttempts = 0;
    var resizeDebounce = null;

    function get_term_container() {
        return document.getElementById("term");
    }

    function get_term_wrapper() {
        return document.getElementById("term-wrapper") || get_term_container();
    }

    function log_debug(message, data) {
        if (data) {
            console.debug("[webrepl_tweaks] " + message, data);
            return;
        }
        console.debug("[webrepl_tweaks] " + message);
    }

    function get_cell_height(term) {
        var core = term && term._core && term._core._renderService;
        var dimensions = core && core.dimensions;
        var cellHeight = dimensions && dimensions.actualCellHeight;
        if (cellHeight) {
            return cellHeight;
        }
        return 16;
    }

    function calculate_dynamic_rows(term) {
        var wrapper = get_term_wrapper();
        var termContainer = get_term_container();
        if (!wrapper || !termContainer) {
            log_debug("missing wrapper or term container", {
                wrapper: !!wrapper,
                termContainer: !!termContainer
            });
            return null;
        }
        var rect = wrapper.getBoundingClientRect();
        var height = rect.height || wrapper.clientHeight || window.innerHeight;
        var style = window.getComputedStyle(termContainer);
        var paddingTop = parseFloat(style.paddingTop) || 0;
        var paddingBottom = parseFloat(style.paddingBottom) || 0;
        var contentHeight = height - paddingTop - paddingBottom;
        var cellHeight = get_cell_height(term);
        var rows = Math.floor(contentHeight / cellHeight) - 2;
        log_debug("row calculation", {
            wrapperHeight: height,
            paddingTop: paddingTop,
            paddingBottom: paddingBottom,
            contentHeight: contentHeight,
            cellHeight: cellHeight,
            calculatedRows: rows,
            safetyRows: 2
        });
        if (!rows || rows < 2) {
            return null;
        }
        return rows;
    }

    function resize_term_rows() {
        if (!window.term || !window.term.resize) {
            log_debug("term not ready");
            return false;
        }
        var rows = calculate_dynamic_rows(window.term);
        if (rows === null) {
            log_debug("skip resize (rows null)");
            return false;
        }
        var cols = window.term.cols || 80;
        if (window.term.rows !== rows) {
            log_debug("resize term", { cols: cols, rows: rows });
            window.term.resize(cols, rows);
        } else {
            log_debug("rows unchanged", { rows: rows });
        }
        return true;
    }

    function schedule_resize_debounced(reason) {
        if (resizeDebounce) {
            window.clearTimeout(resizeDebounce);
        }
        resizeDebounce = window.setTimeout(function() {
            resizeDebounce = null;
            log_debug("resize tick", { reason: reason || "unknown" });
            resize_term_rows();
        }, 100);
    }

    function wait_for_term_ready() {
        if (window.term && window.term.resize) {
            schedule_resize_debounced("term-ready");
            if (resize_term_rows()) {
                return;
            }
        }
        if (readyAttempts >= maxReadyAttempts) {
            log_debug("giving up waiting for term");
            return;
        }
        readyAttempts += 1;
        window.requestAnimationFrame(wait_for_term_ready);
    }

    window.addEventListener("load", function() {
        log_debug("window load");
        wait_for_term_ready();
        schedule_resize_debounced("load");
    });

    window.addEventListener("resize", function() {
        schedule_resize_debounced("window-resize");
    });
}).call(this);
