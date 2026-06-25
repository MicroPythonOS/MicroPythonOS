import logging

import lvgl as lv

from mpos import Activity, DisplayMetrics
logger = logging.getLogger(__name__)


class ShowNpubQRActivity(Activity):
    """Activity that computes npub from nsec and displays it as a QR code."""

    def onCreate(self):
        try:
            prefs = self.getIntent().extras.get("prefs")
            nsec = prefs.get_string("nostr_nsec") if prefs else None

            if not nsec:
                self._show_error("No nsec configured")
                return

            from nostr.key import PrivateKey

            if nsec.startswith("nsec1"):
                private_key = PrivateKey.from_nsec(nsec)
            else:
                private_key = PrivateKey(bytes.fromhex(nsec))

            npub = private_key.public_key.bech32()

            qr_size = round(DisplayMetrics.min_dimension() * 0.9)
            # Reuse FullscreenQR via composition: build its screen manually so
            # we can return to the settings screen instead of finishing the app.
            screen = lv.obj()
            screen.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
            screen.set_scroll_dir(lv.DIR.NONE)
            screen.add_event_cb(lambda e: self.finish(), lv.EVENT.CLICKED, None)
            big_qr = lv.qrcode(screen)
            big_qr.set_size(qr_size)
            big_qr.center()
            big_qr.update(npub, len(npub))
            self.setContentView(screen)
        except Exception as e:
            logger.exception("ShowNpubQRActivity failed: %s", e)
            self._show_error(f"Error: {e}")

    def _show_error(self, text):
        screen = lv.obj()
        label = lv.label(screen)
        label.set_text(text)
        label.center()
        self.setContentView(screen)
