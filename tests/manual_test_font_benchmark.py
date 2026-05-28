import unittest

import lvgl as lv

from mpos import FontManager
from mpos.ui.testing import GraphicalTestCase, wait_for_render


class TestManualFontBenchmark(GraphicalTestCase):
    def _build_screen(self, font):
        screen = lv.obj()
        screen.set_size(320, 240)
        screen.set_scroll_dir(lv.DIR.VER)
        screen.set_scrollbar_mode(lv.SCROLLBAR_MODE.AUTO)

        label = lv.label(screen)
        label.set_width(300)
        label.set_long_mode(lv.label.LONG_MODE.WRAP)
        label.set_style_text_font(font, lv.PART.MAIN)

        lines = []
        for i in range(80):
            lines.append(
                "{} Build info line {}: API 7.0.0 board ESP32 mem 123456 bytes".format(
                    lv.SYMBOL.HOME, i
                )
            )
        label.set_text("\n".join(lines))
        return screen

    def _measure_scroll_ms(self, font, steps=160):
        screen = self._build_screen(font)
        lv.screen_load(screen)
        wait_for_render(6)

        start_us = lv.tick_get() * 1000
        for i in range(steps):
            screen.scroll_to_y(i * 6, False)
            wait_for_render(1)
        end_us = lv.tick_get() * 1000
        return (end_us - start_us) / 1000

    def test_manual_benchmark(self):
        base = FontManager.getFont(size=14, family="Montserrat", emoji=False)
        composed = FontManager.getFont(size=14, family="Montserrat", emoji="on")
        auto_plain = FontManager.getFont(size=14, family="Montserrat", emoji="auto")

        # Warm-up for caches and decoder setup.
        self._measure_scroll_ms(base, steps=20)
        self._measure_scroll_ms(composed, steps=20)
        self._measure_scroll_ms(auto_plain, steps=20)

        t_base = self._measure_scroll_ms(base)
        t_composed = self._measure_scroll_ms(composed)
        t_auto_plain = self._measure_scroll_ms(auto_plain)

        ratio = (t_composed / t_base) if t_base > 0 else 0
        ratio_auto = (t_auto_plain / t_base) if t_base > 0 else 0
        print("BENCH font emoji=False: {} ms".format(int(t_base)))
        print("BENCH font emoji=True:  {} ms".format(int(t_composed)))
        print("BENCH font emoji=auto/plain-text: {} ms".format(int(t_auto_plain)))
        print("BENCH ratio emoji_true/false: {:.2f}x".format(ratio))
        print("BENCH ratio auto_plain/false: {:.2f}x".format(ratio_auto))

        self.assertTrue(t_base >= 0)


if __name__ == "__main__":
    unittest.main()
