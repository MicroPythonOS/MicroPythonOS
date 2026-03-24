// Set terminal height dynamically, without modifying webrepl.js
(function() {
    var maxReadyAttempts = 90;
    var readyAttempts = 0;
    var resizeScheduled = false;
    var resizeDebounce = null;

    function get_term_container() {
        return document.getElementById('term');
    }

    // Wrapper keeps a fixed height; rows are derived from its rendered height.
    function get_term_wrapper() {
        return document.getElementById('term-wrapper') || get_term_container();
    }

    // Compute rows once on load/resize using wrapper height and terminal padding.
    function calculate_dynamic_rows() {
        var wrapper = get_term_wrapper();
        var termContainer = get_term_container();
        if (!wrapper || !termContainer) {
            return null;
        }
        var rect = wrapper.getBoundingClientRect();
        var height = rect.height || wrapper.clientHeight || window.innerHeight;
        var style = window.getComputedStyle(termContainer);
        var paddingTop = parseFloat(style.paddingTop) || 0;
        var paddingBottom = parseFloat(style.paddingBottom) || 0;
        var contentHeight = height - paddingTop - paddingBottom;
        return Math.max(24, Math.min(80, (contentHeight - 20) / 12)) | 0;
    }

    function resize_term_rows() {
        if (!window.term || !window.term.resize) {
            return false;
        }
        var rows = calculate_dynamic_rows();
        if (rows === null) {
            return false;
        }
        var cols = window.term.cols || 80;
        if (window.term.rows !== rows) {
            window.term.resize(cols, rows);
        }
        return true;
    }

    function schedule_resize() {
        if (resizeScheduled) {
            return;
        }
        resizeScheduled = true;
        window.requestAnimationFrame(function() {
            resizeScheduled = false;
            resize_term_rows();
        });
    }

    function schedule_resize_debounced() {
        if (resizeDebounce) {
            window.clearTimeout(resizeDebounce);
        }
        resizeDebounce = window.setTimeout(function() {
            resizeDebounce = null;
            schedule_resize();
        }, 80);
    }

    function wait_for_term_ready() {
        if (window.term && window.term.resize) {
            schedule_resize_debounced();
            if (resize_term_rows()) {
                return;
            }
        }
        if (readyAttempts >= maxReadyAttempts) {
            return;
        }
        readyAttempts += 1;
        window.requestAnimationFrame(wait_for_term_ready);
    }

    window.addEventListener('load', function() {
        wait_for_term_ready();
        schedule_resize_debounced();
    });

    window.addEventListener('resize', function() {
        schedule_resize_debounced();
    });
}).call(this);
