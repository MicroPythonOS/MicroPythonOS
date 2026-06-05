"""
Diagnostic test for screenshot rendering.
Tests basic LVGL rendering to understand what's visible in screenshots.
"""
import unittest
import lvgl as lv
from mpos import capture_screenshot, wait_for_render
from mpos.ui.testing import simulate_click


class TestScreenshotDiagnostic(unittest.TestCase):
    """Diagnose screenshot rendering issues."""

    def setUp(self):
        self.orig_screen = lv.screen_active()

    def tearDown(self):
        lv.screen_load(self.orig_screen)
        wait_for_render(5)

    def test_simple_label_renders(self):
        screen = lv.obj()
        screen.set_size(320, 240)
        screen.set_style_bg_color(lv.color_hex(0x000011), 0)

        label = lv.label(screen)
        label.set_text("TEST LABEL GREEN")
        label.set_style_text_color(lv.color_hex(0x00FF00), 0)
        label.center()

        lv.screen_load(screen)
        wait_for_render(20)

        buf = capture_screenshot(width=320, height=240, color_format=lv.COLOR_FORMAT.RGB888)

        # Scan all pixels for bright green (should be > 200 in G channel)
        green_pixels = 0
        for i in range(0, len(buf), 3):
            r = buf[i + 2]
            g = buf[i + 1]
            b = buf[i]
            if g > 200 and r < 100 and b < 100:
                green_pixels += 1

        print(f"\nGreen pixels found: {green_pixels} out of {len(buf)//3}")
        self.assertTrue(green_pixels > 0, "No green pixels found - label text not rendering in screenshot!")

    def test_canvas_pixel_renders(self):
        screen = lv.obj()
        screen.set_size(320, 240)
        screen.set_style_bg_color(lv.color_hex(0x000011), 0)

        canvas = lv.canvas(screen)
        canvas.set_size(24, 18)
        buf = bytearray(24 * 18 * 4)
        canvas.set_buffer(buf, 24, 18, lv.COLOR_FORMAT.NATIVE)
        canvas.set_style_border_width(0, 0)
        canvas.set_style_bg_opa(lv.OPA.TRANSP, 0)
        canvas.set_pos(148, 111)

        canvas.set_px(0, 0, lv.color_hex(0x00FFFF), lv.OPA.COVER)
        canvas.set_px(12, 9, lv.color_hex(0x00FFFF), lv.OPA.COVER)

        lv.screen_load(screen)
        wait_for_render(20)

        buf = capture_screenshot(width=320, height=240, color_format=lv.COLOR_FORMAT.RGB888)

        cyan_pixels = 0
        for i in range(0, len(buf), 3):
            r = buf[i + 2]
            g = buf[i + 1]
            b = buf[i]
            if g > 200 and b > 200 and r < 100:
                cyan_pixels += 1

        print(f"\nCyan pixels found: {cyan_pixels} out of {len(buf)//3}")
        self.assertTrue(cyan_pixels > 0, "No cyan pixels found - canvas set_px() not rendering in screenshot!")

    def test_layer_top_content_renders(self):
        screen = lv.obj()
        screen.set_size(320, 240)
        screen.set_style_bg_color(lv.color_hex(0x000011), 0)
        lv.screen_load(screen)

        top_modal = lv.obj(lv.layer_top())
        top_modal.set_size(320, 240)
        top_modal.set_pos(0, 0)
        top_modal.set_style_bg_color(lv.color_hex(0x000000), 0)
        top_modal.set_style_bg_opa(160, 0)
        top_modal.set_style_border_width(0, 0)

        popup = lv.obj(top_modal)
        popup.set_size(200, 100)
        popup.set_style_bg_color(lv.color_hex(0x333333), 0)
        popup.set_style_border_color(lv.color_hex(0x00FF00), 0)
        popup.set_style_border_width(2, 0)
        popup.set_style_radius(10, 0)
        popup.center()

        q = lv.label(popup)
        q.set_text("WHITE TEXT ON LAYER_TOP")
        q.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
        q.align(lv.ALIGN.TOP_MID, 0, 15)

        wait_for_render(20)

        buf = capture_screenshot(width=320, height=240, color_format=lv.COLOR_FORMAT.RGB888)

        white_pixels = 0
        for i in range(0, len(buf), 3):
            r = buf[i + 2]
            g = buf[i + 1]
            b = buf[i]
            if r > 200 and g > 200 and b > 200:
                white_pixels += 1

        print(f"\nWhite pixels found in center: {white_pixels} out of {len(buf)//3}")
        self.assertTrue(white_pixels > 0, "No white pixels found - layer_top content not compositing in screenshot!")

    def test_label_with_screen_load_anim(self):
        screen = lv.obj()
        screen.set_size(320, 240)
        screen.set_style_bg_color(lv.color_hex(0x000011), 0)

        label = lv.label(screen)
        label.set_text("ANIM TEST GREEN")
        label.set_style_text_color(lv.color_hex(0x00FF00), 0)
        label.center()

        lv.screen_load_anim(screen, lv.SCREEN_LOAD_ANIM.OVER_LEFT, 500, 0, False)
        wait_for_render(60)

        buf = capture_screenshot(width=320, height=240, color_format=lv.COLOR_FORMAT.RGB888)

        green_pixels = 0
        for i in range(0, len(buf), 3):
            r = buf[i + 2]
            g = buf[i + 1]
            b = buf[i]
            if g > 200 and r < 100 and b < 100:
                green_pixels += 1

        print(f"\nAnim test: Green pixels found: {green_pixels} out of {len(buf)//3}")
        self.assertTrue(green_pixels > 0, "No green pixels with screen_load_anim!")

    def test_space_invaders_start_screen(self):
        from mpos import AppManager
        result = AppManager.start_app("com.micropythonos.space_invaders")
        self.assertTrue(result, "SpaceInvaders failed to start!")

        wait_for_render(30)

        buf = capture_screenshot(width=320, height=240, color_format=lv.COLOR_FORMAT.RGB888)

        green_pixels = 0
        total = len(buf) // 3
        for i in range(0, len(buf), 3):
            r = buf[i + 2]
            g = buf[i + 1]
            b = buf[i]
            if g > 200 and r < 100 and b < 100:
                green_pixels += 1

        print(f"\nSpaceInvaders: Green pixels found: {green_pixels} out of {total}")
        self.assertTrue(green_pixels > 0, "No green pixels in SpaceInvaders screenshot!")

        # Also scan for any bright content in the game area (y 28-225)
        bright_center = 0
        for y in range(28, 225):
            for x in range(0, 320):
                idx = (y * 320 + x) * 3
                r = buf[idx + 2]
                g = buf[idx + 1]
                b = buf[idx]
                if r > 100 or g > 100 or b > 100:
                    bright_center += 1
        print(f"SpaceInvaders: Bright pixels in game area: {bright_center}")

    def test_space_invaders_no_wait(self):
        """Test without wait_for_render() - simulating controller behavior."""
        from mpos import AppManager
        AppManager.start_app("com.micropythonos.space_invaders")

        buf = capture_screenshot(width=320, height=240, color_format=lv.COLOR_FORMAT.RGB888)

        green_pixels = 0
        total = len(buf) // 3
        for i in range(0, len(buf), 3):
            r = buf[i + 2]
            g = buf[i + 1]
            b = buf[i]
            if g > 200 and r < 100 and b < 100:
                green_pixels += 1

        bright_center = 0
        for y in range(28, 225):
            for x in range(0, 320):
                idx = (y * 320 + x) * 3
                r = buf[idx + 2]
                g = buf[idx + 1]
                b = buf[idx]
                if r > 100 or g > 100 or b > 100:
                    bright_center += 1

        print(f"\nNo-wait: Green pixels: {green_pixels}, Bright in game area: {bright_center} out of {total}")

    def test_modal_inside_parent(self):
        """Reproduce SpaceInvaders scernario: modal inside game_area with label."""
        screen = lv.obj()
        screen.set_size(320, 240)
        screen.set_style_bg_color(lv.color_hex(0x000011), 0)

        game_area = lv.obj(screen)
        game_area.set_size(320, 197)
        game_area.set_pos(0, 28)
        game_area.set_style_bg_color(lv.color_hex(0x000008), 0)
        game_area.set_style_border_width(0, 0)
        game_area.set_style_radius(0, 0)
        game_area.set_style_clip_corner(True, 0)

        modal = lv.obj(game_area)
        modal.set_size(320, 197)
        modal.set_pos(0, 0)
        modal.set_style_bg_color(lv.color_hex(0x000011), 0)
        modal.set_style_border_width(0, 0)
        modal.set_style_radius(0, 0)

        label = lv.label(modal)
        label.set_text("SPACE INVADERS\n\nHigh Score: 0")
        label.set_style_text_color(lv.color_hex(0x00FF00), 0)
        label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        label.set_long_mode(lv.label.LONG_MODE.WRAP)
        label.set_size(300, 177)
        label.center()

        lv.screen_load(screen)
        wait_for_render(20)

        buf = capture_screenshot(width=320, height=240, color_format=lv.COLOR_FORMAT.RGB888)

        green_pixels = 0
        for i in range(0, len(buf), 3):
            r = buf[i + 2]
            g = buf[i + 1]
            b = buf[i]
            if g > 200 and r < 100 and b < 100:
                green_pixels += 1

        total = len(buf) // 3
        print(f"\nModal test: Green pixels: {green_pixels} out of {total}")
        print(f"Modal test: Modal bg (0x000011) should cover game_area bg (0x000008)")

        # Check game_area region for modal bg vs game_area bg
        modal_bg = 0
        game_bg = 0
        for y in range(28, 225):
            for x in range(0, 320):
                idx = (y * 320 + x) * 3
                r, g, b = buf[idx + 2], buf[idx + 1], buf[idx]
                if (r, g, b) == (0, 0, 17):   # 0x000011
                    modal_bg += 1
                elif (r, g, b) == (0, 0, 8):  # 0x000008
                    game_bg += 1
        print(f"Modal bg (0x000011) pixels: {modal_bg}")
        print(f"Game_area bg (0x000008) pixels: {game_bg}")

        self.assertTrue(green_pixels > 0, "No green text in modal - start screen text not rendering!")

    def test_screen_load_anim_immediate_screenshot(self):
        """Reproduce controller's screenshot without waiting for load_anim."""
        screen = lv.obj()
        screen.set_size(320, 240)
        screen.set_style_bg_color(lv.color_hex(0x000011), 0)

        game_area = lv.obj(screen)
        game_area.set_size(320, 197)
        game_area.set_pos(0, 28)
        game_area.set_style_bg_color(lv.color_hex(0x000008), 0)
        game_area.set_style_border_width(0, 0)
        game_area.set_style_radius(0, 0)
        game_area.set_style_clip_corner(True, 0)

        modal = lv.obj(game_area)
        modal.set_size(320, 197)
        modal.set_pos(0, 0)
        modal.set_style_bg_color(lv.color_hex(0x000011), 0)
        modal.set_style_border_width(0, 0)
        modal.set_style_radius(0, 0)

        label = lv.label(modal)
        label.set_text("SPACE INVADERS\n\nHigh Score: 0")
        label.set_style_text_color(lv.color_hex(0x00FF00), 0)
        label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        label.set_long_mode(lv.label.LONG_MODE.WRAP)
        label.set_size(300, 177)
        label.center()

        lv.screen_load_anim(screen, lv.SCREEN_LOAD_ANIM.OVER_LEFT, 500, 0, False)

        # IMMEDIATE screenshot - no wait_for_render at all
        buf = capture_screenshot(width=320, height=240, color_format=lv.COLOR_FORMAT.RGB888)

        green_pixels = 0
        for i in range(0, len(buf), 3):
            r = buf[i + 2]
            g = buf[i + 1]
            b = buf[i]
            if g > 200 and r < 100 and b < 100:
                green_pixels += 1

        total = len(buf) // 3
        print(f"\nImmediate anim: Green pixels: {green_pixels} out of {total}")
        self.assertTrue(green_pixels > 0, "No green in immediate screenshot after screen_load_anim!")

    def test_lv_pct_before_load(self):
        """Test if lv.pct(100) resolves to 0 before screen is loaded."""
        screen = lv.obj()
        screen.set_style_bg_color(lv.color_hex(0x001100), 0)

        child = lv.obj(screen)
        child.set_size(lv.pct(100), 50)
        child.set_style_bg_color(lv.color_hex(0x00FF00), 0)
        child.set_pos(0, 50)

        w_before = child.get_width()
        h_before = child.get_height()
        print(f"\nBefore screen_load: width={w_before}, height={h_before}")

        lv.screen_load(screen)
        w_after_load = child.get_width()
        h_after_load = child.get_height()
        print(f"After screen_load: width={w_after_load}, height={h_after_load}")

        wait_for_render(20)
        w_after_render = child.get_width()
        print(f"After wait_for_render: width={w_after_render}")

        buf = capture_screenshot(width=320, height=240, color_format=lv.COLOR_FORMAT.RGB888)

        # Check the y=50 line for green pixels (child bg should be green at width=320)
        green_on_line = 0
        for x in range(320):
            idx = (50 * 320 + x) * 3
            r = buf[idx + 2]
            g = buf[idx + 1]
            b = buf[idx]
            if g > 200 and r < 100 and b < 100:
                green_on_line += 1
        print(f"Green pixels on line y=50: {green_on_line} (should be 320 if width=320, or 0 if width=0)")

        self.assertTrue(w_before > 0 or w_after_render > 0, 
            "lv.pct(100) child always has 0 width - likely the SpaceInvaders bug!")

    def test_space_invaders_tap_to_start_game(self):
        from mpos import AppManager
        result = AppManager.start_app("com.micropythonos.space_invaders")
        self.assertTrue(result, "SpaceInvaders failed to start!")
        wait_for_render(30)

        # Tap center of screen to start the game
        simulate_click(160, 120)
        wait_for_render(30)

        buf = capture_screenshot(width=320, height=240, color_format=lv.COLOR_FORMAT.RGB888)
        total = len(buf) // 3

        green_pixels = 0
        cyan_pixels = 0
        bright_pixels = 0
        for i in range(0, len(buf), 3):
            r = buf[i + 2]
            g = buf[i + 1]
            b = buf[i]
            if g > 200 and r < 100 and b < 100:
                green_pixels += 1
            if g > 200 and b > 200 and r < 100:
                cyan_pixels += 1
            if r > 50 or g > 50 or b > 50:
                bright_pixels += 1

        # Count bright pixels in game area region (y 28-225)
        game_area_bright = 0
        for y in range(28, 225):
            for x in range(0, 320):
                idx = (y * 320 + x) * 3
                r = buf[idx + 2]
                g = buf[idx + 1]
                b = buf[idx]
                if r > 50 or g > 50 or b > 50:
                    game_area_bright += 1

        print(f"\nGame playing - Green: {green_pixels}, Cyan: {cyan_pixels}, "
              f"Bright total: {bright_pixels}, Bright in game area: {game_area_bright} out of {total}")
        # Game should have substantially more content than start screen
        self.assertTrue(game_area_bright > 500,
            f"Game area only has {game_area_bright} bright pixels - game not rendering after tap!")



