import logging

import lvgl as lv

from mpos import Activity, DisplayMetrics

logger = logging.getLogger(__name__)


class ShowNsecQRActivity(Activity):
    """Activity that displays the configured nsec as a QR code."""

    def onCreate(self):
        try:
            prefs = self.getIntent().extras.get("prefs")
            secret = prefs.get_string("nostr_nsec") if prefs else None

            if not secret:
                self._show_error("No nsec configured")
                return

            from nostr.key import PrivateKey

            if secret.startswith("nsec1"):
                private_key = PrivateKey.from_nsec(secret)
            else:
                private_key = PrivateKey(bytes.fromhex(secret))

            nsec = private_key.bech32()

            qr_size = round(DisplayMetrics.min_dimension() * 0.6)
            screen = lv.obj()
            screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
            screen.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
            screen.set_style_pad_all(DisplayMetrics.pct_of_width(2), lv.PART.MAIN)
            screen.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
            screen.set_scroll_dir(lv.DIR.NONE)
            screen.add_event_cb(lambda e: self.finish(), lv.EVENT.CLICKED, None)
            warn_lbl = lv.label(screen)
            warn_lbl.set_text("WARNING: This is your private key. Anyone who sees it can steal your identity and funds.")
            warn_lbl.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)
            warn_lbl.set_long_mode(lv.label.LONG_MODE.WRAP)
            warn_lbl.set_width(lv.pct(100))
            warn_lbl.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.PART.MAIN)
            big_qr = lv.qrcode(screen)
            big_qr.set_size(qr_size)
            big_qr.update(nsec, len(nsec))
            self.setContentView(screen)
        except Exception as e:
            logger.exception("ShowNsecQRActivity failed: %s", e)
            self._show_error(f"Error: {e}")

    def _show_error(self, text):
        screen = lv.obj()
        label = lv.label(screen)
        label.set_text(text)
        label.center()
        self.setContentView(screen)
