0.0.9
=====
- UI: add visual cues during back/top swipe gestures
- Settings: add Timezone configuration
- Draw: new app for simple drawing on a canvas
- IMU: new app for showing data from the Intertial Measurement Unit ("Accellerometer")


0.0.8
=====
- Move wifi icon to the right-hand side
- Power off camera after boot and before deepsleep to conserve power
- Settings: add 20 common theme colors in dropdown list

0.0.7
=====
- Update battery icon every 5 seconds depending on VBAT/BAT_ADC
- Add "Power" off button in menu drawer

0.0.6
=====
- Scale button size in drawer for bigger screens
- Show "Brightness" text in drawer
- Add builtin "Settings" app with settings for Light/Dark Theme, Theme Color, Restart to Bootloader
- Add "Settings" button to drawer that opens settings app
- Save and restore "Brightness" setting
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
- Handle IO0 "BOOT button" so long-press starts bootloader mode for updating firmware over USB

0.0.1
=====
- Initial release

