0.3.1
=====
- OSUpdate app: fix typo that caused update rollback
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
- Remove 'long press pin 0' for bootloader mode; either use the Settings app or keep it pressed while pressing and releasing the 'RESET' button
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

