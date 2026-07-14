import json
import logging

import lvgl as lv

from mpos import Activity, DisplayMetrics, MposKeyboard

from .profile_cache import ProfileCache

logger = logging.getLogger(__name__)


class ProfileActivity(Activity):

    _name_ta = None
    _about_ta = None
    _keyboard = None

    def onCreate(self):
        prefs = self.getIntent().extras.get("prefs")
        nsec = prefs.get_string("nostr_nsec") if prefs else None

        screen = lv.obj()
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_style_pad_all(DisplayMetrics.pct_of_width(2), lv.PART.MAIN)
        screen.set_style_pad_gap(DisplayMetrics.pct_of_width(1), lv.PART.MAIN)

        title = lv.label(screen)
        title.set_text("Edit Your Profile")
        title.set_style_text_font(lv.font_montserrat_18, lv.PART.MAIN)

        name_lbl = lv.label(screen)
        name_lbl.set_text("Display Name")
        name_lbl.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)

        self._name_ta = lv.textarea(screen)
        self._name_ta.set_width(lv.pct(100))
        self._name_ta.set_height(DisplayMetrics.pct_of_height(6))
        self._name_ta.set_placeholder_text("Your name")
        self._name_ta.set_max_length(50)
        self._name_ta.set_one_line(True)
        self._name_ta.add_event_cb(
            lambda e: self._show_keyboard(self._name_ta), lv.EVENT.CLICKED, None
        )

        about_lbl = lv.label(screen)
        about_lbl.set_text("About")
        about_lbl.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)

        self._about_ta = lv.textarea(screen)
        self._about_ta.set_width(lv.pct(100))
        self._about_ta.set_height(DisplayMetrics.pct_of_height(12))
        self._about_ta.set_placeholder_text("A short bio")
        self._about_ta.set_max_length(160)
        self._about_ta.add_event_cb(
            lambda e: self._show_keyboard(self._about_ta), lv.EVENT.CLICKED, None
        )

        save_btn = lv.button(screen)
        save_lbl = lv.label(save_btn)
        save_lbl.set_text("Publish Profile")
        save_lbl.center()
        save_btn.add_event_cb(lambda e: self._save(nsec), lv.EVENT.CLICKED, None)

        if nsec:
            cache = ProfileCache.get_instance()
            try:
                from nostr.key import PrivateKey

                pk = PrivateKey.from_nsec(nsec)
                own_hex = pk.public_key.hex()
                profile = cache.get_profile(own_hex)
                if profile:
                    if profile.get("display_name"):
                        self._name_ta.set_text(profile["display_name"])
                    elif profile.get("name"):
                        self._name_ta.set_text(profile["name"])
                    if profile.get("about"):
                        self._about_ta.set_text(profile["about"])
            except Exception as e:
                logger.warning("Failed to load own profile: %s", e)

        self.setContentView(screen)

    def _show_keyboard(self, ta):
        if self._keyboard:
            self._keyboard.delete()
        self._keyboard = MposKeyboard()
        self._keyboard.show(ta)

    def _save(self, nsec):
        display_name = self._name_ta.get_text().strip()
        about = self._about_ta.get_text().strip()

        if not display_name and not about:
            return

        content = {}
        if display_name:
            content["name"] = display_name
            content["display_name"] = display_name
        if about:
            content["about"] = about

        from .nostr_service import NostrManager

        manager = NostrManager.get_instance()
        try:
            manager.publish_metadata(json.dumps(content))
        except Exception as e:
            logger.error("Failed to publish profile: %s", e)
            return

        if nsec:
            try:
                from nostr.key import PrivateKey

                pk = PrivateKey.from_nsec(nsec)
                own_hex = pk.public_key.hex()
                profile = {"display_name": display_name, "about": about}
                profile["name"] = display_name
                import time as _time

                try:
                    from nostr.event import Event

                    profile["added_at"] = Event.epoch_seconds()
                except Exception:
                    profile["added_at"] = int(_time.time())
                cache = ProfileCache.get_instance()
                cache._profiles[own_hex] = profile
                cache._save()
            except Exception as e:
                logger.warning("Failed to update own profile in cache: %s", e)

        if self._keyboard:
            try:
                self._keyboard.delete()
            except Exception:
                pass
            self._keyboard = None
        self.finish()

    def onDestroy(self, screen):
        if self._keyboard:
            try:
                self._keyboard.delete()
            except Exception:
                pass
            self._keyboard = None
