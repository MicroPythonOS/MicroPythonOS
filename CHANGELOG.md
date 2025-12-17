0.5.2
=====
- AudioFlinger: optimize WAV volume scaling for speed and immediately set volume
- AudioFlinger: eliminate thread by using TaskManager (asyncio)
- AppStore app: eliminate all thread by using TaskManager
- AppStore app: add support for BadgeHub backend
- OSUpdate app: show download speed
- API: add TaskManager that wraps asyncio
- API: add DownloadManager that uses TaskManager
- API: use aiorepl to eliminate another thread


0.5.1
=====
- Fri3d Camp 2024 Board: add startup light and sound
- Fri3d Camp 2024 Board: workaround ADC2+WiFi conflict by temporarily disable WiFi to measure battery level
- Fri3d Camp 2024 Board: improve battery monitor calibration to fix 0.1V delta
- Fri3d Camp 2024 Board: add WSEN-ISDS 6-Axis Inertial Measurement Unit (IMU) support (including temperature)
- API: improve and cleanup animations
- API: SharedPreferences: add erase_all() function
- API: add defaults handling to SharedPreferences and only save non-defaults
- API: restore sys.path after starting app
- API: add AudioFlinger for audio playback (i2s DAC and buzzer)
- API: add LightsManager for multicolor LEDs
- API: add SensorManager for generic handling of IMUs and temperature sensors
- UI: back swipe gesture closes topmenu when open (thanks, @Mark19000 !)
- About app: add free, used and total storage space info
- AppStore app: remove unnecessary scrollbar over publisher's name
- Camera app: massive overhaul!
    - Lots of settings (basic, advanced, expert)
    - Enable decoding of high density QR codes (like Nostr Wallet Connect) from small sizes (like mobile phone screens)
    - Even dotted, logo-ridden and scratched *pictures* of QR codes are now decoded properly!
- ImageView app: add delete functionality
- ImageView app: add support for grayscale images
- OSUpdate app: pause download when wifi is lost, resume when reconnected
- Settings app: fix un-checking of radio button
- Settings app: add IMU calibration
- Wifi app: simplify on-screen keyboard handling, fix cancel button handling

0.5.0
=====
- ESP32: one build to rule them all; instead of 2 builds per supported board, there is now one single build that identifies and initializes the board at runtime!
- MposKeyboard: fix q, Q, 1 and ~ button unclickable bug
- MposKeyboard: increase font size from 16 to 20
- MposKeyboard: use checkbox instead of newline symbol for 'OK, Ready'
- MposKeyboard: bigger space bar
- OSUpdate app: simplify by using ConnectivityManager
- OSUpdate app: adapt to new device IDs
- ImageView app: improve error handling
- Settings app: tweak font size
- Settings app: add 'format internal data partition' option
- Settings app: fix checkbox handling with buttons
- UI: pass clicks on invisible 'gesture swipe start' are to underlying widget
- UI: only show back and down gesture icons on swipe, not on tap
- UI: double size of back and down swipe gesture starting areas for easier gestures
- UI: increase navigation gesture sensitivity
- UI: prevent visual glitches in animations
- API: add facilities for instrumentation (screengrabs, mouse clicks)
- API: move WifiService to mpos.net
- API: remove fonts to reduce size
- API: replace font_montserrat_28 with font_montserrat_28_compressed to reduce size
- API: improve SD card error handling
- WifiService: connect to strongest networks first

0.4.0
=====
- Add custom MposKeyboard with more than 50% bigger buttons, great for tiny touch screens!
- Apply theme changes (dark mode, color) immediately after saving
- About app: add a bit more info
- Camera app: fix one-in-two 'camera image stays blank' issue
- OSUpdate app: enable scrolling with joystick/arrow keys
- OSUpdate app: Major rework with improved reliability and user experience
    - add WiFi monitoring - shows 'Waiting for WiFi...' instead of error when no connection
    - add automatic pause/resume on WiFi loss during downloads using HTTP Range headers
    - add user-friendly error messages with specific guidance for each error type
    - add 'Check Again' button for easy retry after errors
    - add state machine for better app state management
    - add comprehensive test coverage (42 tests: 31 unit tests + 11 graphical tests)
    - refactor code into testable components (NetworkMonitor, UpdateChecker, UpdateDownloader)
    - improve download error recovery with progress preservation
    - improve timeout handling (5-minute wait for WiFi with clear messaging)
- Tests: add test infrastructure with mock classes for network, HTTP, and partition operations
- Tests: add graphical test helper utilities for UI verification and screenshot capture
- API: change 'display' to mpos.ui.main_display
- API: change mpos.ui.th to mpos.ui.task_handler
- waveshare-esp32-s3-touch-lcd-2: power off camera at boot to conserve power
- waveshare-esp32-s3-touch-lcd-2: increase touch screen input clock frequency from 100kHz to 400kHz

0.3.2
=====
- Settings app: add 'Auto Start App' setting
- Tweak gesture navigation to trigger back and top menu more easily
- Rollback OTA update if launcher fails to start
- Rename 'Home' to 'Launch' in top menu drawer
- Fri3d-2024 Badge: use same SPI freq as Waveshare 2 inch for uniformity
- ESP32: reduce drawing frequency by increasing task_handler duration from 1ms to 5ms
- Rework MicroPython WebSocketApp websocket-client library using uasyncio
- Rework MicroPython python-nostr library using uasyncio
- Update aiohttp_ws library to 0.0.6
- Add fragmentation support for aiohttp_ws library

Known issues:
- Fri3d-2024 Badge: joystick arrow up ticks a radio button (workaround: un-tick the radio button)

0.3.1
=====
- OSUpdate app: fix typo that prevented update rollback from being cancelled
- Fix 'Home' button in top menu not stopping all apps
- Update micropython-nostr library to fix epoch time on ESP32 and NWC event kind

0.3.0
=====
- OSUpdate app: now gracefully handles the user closing the app mid-update instead of freezing
- Launcher app: much faster thanks to PackageManager + UI only rebuilt when apps actually change
- AppStore app: improved stability + icons for already-installed apps are shown instantly (no download needed)
- API: Add SDCardManager for SD Card support
- API: add PackageManager to (un)install MPK packages
- API: split mpos.ui into logical components
- Remove 'long press IO0 button' to activate bootloader mode; either use the Settings app (very convenient) or keep it pressed while plugging in the USB cable (or briefly pressing the reset button)
- Increase framerate on ESP32 by lowering task_handler duration from 5ms to 1ms
- Throttle per-frame async_call() to prevent apps from overflowing memory
- Overhaul build system and docs: much simplier (single clone and script run), add MacOS support, build with GitHub Workflow, automatic tests, etc.

0.2.1
=====
- Settings app: fix stray /cat in Europe/Brussels timezone
- Launcher app: fix handling of empty filesystem without apps

0.2.0
=====
- Fix KeyPad focus handling for devices without touch screen like the Fri3d Camp 2024 Badge
- Use direction arrows for more intuitive navigation instead of Y/A or pageup/pagedown for previous/next
- About app: enable scrolling using arrow keys so off-screen info can be viewed
- About app: add info about freezefs compiled-in filesystem
- AppStore app: don't update UI after the user has closed the app
- Launcher app: improve error handling
- Wifi app: cleanup and improve keyboard and focus handling
- Wifi app: improve different screensize handling

0.1.1
=====
- Update to MicroPython 1.25.0 and LVGL 9.3.0
- About app: add info about over-the-air partitions
- OSUpdate app: check update depending on current hardware identifier, add 'force update' option, improve user feedback
- AppStore, Camera, Launcher, Settings: adjust for compatibility with LVGL 9.3.0

0.0.11
======
- Merge official Fri3d Camp 2024 Badge support

0.0.10
======
- About app: add machine.freq, unique_id, wake_reason and reset_cause
- Reduce timezones from 400 to 150 to reduce scrolling
- Experimental Fri3d Camp 2024 Badge support

0.0.9
=====
- UI: add visual cues during back/top swipe gestures
- UI: prevent menu drawer button clicks while swiping
- Settings: add Timezone configuration
- Draw: new app for simple drawing on a canvas
- IMU: new app for showing data from the Intertial Measurement Unit ('Accellerometer')
- Camera: speed up QR decoding 4x - thanks @kdmukai!


0.0.8
=====
- Move wifi icon to the right-hand side
- Power off camera after boot and before deepsleep to conserve power
- Settings: add 20 common theme colors in dropdown list

0.0.7
=====
- Update battery icon every 5 seconds depending on VBAT/BAT_ADC
- Add 'Power' off button in menu drawer

0.0.6
=====
- Scale button size in drawer for bigger screens
- Show 'Brightness' text in drawer
- Add builtin 'Settings' app with settings for Light/Dark Theme, Theme Color, Restart to Bootloader
- Add 'Settings' button to drawer that opens settings app
- Save and restore 'Brightness' setting
- AppStore: speed up app installs
- Camera: scale camera image to fit screen on bigger displays
- Camera: show decoded result on-display if QR decoded

0.0.5
=====
- Improve focus group handling while in deskop keyboard mode
- Add filesystem driver for LVGL
- Implement CTRL-V to paste on desktop
- Implement Escape key for back button on desktop
- WiFi: increase size of on-screen keyboard for easier password entry
- WiFi: prevent concurrent operation of auto-connect and Wifi app

0.0.4
=====
- Add left edge swipe gesture for back screen action
- Add animations
- Add support for QR decoding by porting quirc
- Add support for Nostr by porting python-nostr
- Add support for Websockets by porting websocket-client's WebSocketApp 
- Add support for secp256k1 with ecdh by porting and extending secp256k1-embedded
- Change theme from dark to light
- Improve display refresh rate
- Fix aiohttp_ws bug that caused partial websocket data reception
- Add support for on Linux desktop
- Add support for VideoForLinux2 devices (webcams etc) on Linux
- Improve builtin apps: Launcher, WiFi, AppStore and OSUpdate

0.0.3
=====
- appstore: add 'update' button if a new version of an app is available
- appstore: add 'restore' button to restore updated built-in apps to their original built-in version
- launcher: don't show launcher apps and sort alphabetically
- osupdate: show info about update and 'Start OS Update' before updating
- wificonf: scan and connect to wifi in background thread so app stays responsive
- introduce MANIFEST.JSON format for apps
- improve notification bar behavior

0.0.2
=====
- Handle IO0 'BOOT button' so long-press starts bootloader mode for updating firmware over USB

0.0.1
=====
- Initial release

