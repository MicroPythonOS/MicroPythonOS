#!/usr/bin/env python3
from pydbus import SystemBus, Variant
import pydbus
import time
import sys
import json

"""
Librem 5, phosh, python. Give me code to read current battery level.

(and more)

Lets make it class Phone, one method would be reading battery information, one would be reading operator name / signal strength, one would be getting wifi enabled/disabled / AP name.

Can you also get silent mode, pending notifications, and gps coordinates on request?

run this with sudo to work around permission problems

sudo apt install python3-pydbus

sudo mmcli --list-modems
sudo mmcli -m 6 --location-enable-gps-nmea --location-enable-gps-raw
"""



class Phone:
    verbose = False

    def __init__(self):
        self.bus = pydbus.SystemBus()

    def init_sess(self):
        self.sess = pydbus.SessionBus()

    # --- Battery ---
    def get_battery_info(self):
        upower = self.bus.get("org.freedesktop.UPower")
        for dev_path in upower.EnumerateDevices():
            if self.verbose: print("dev_path is", dev_path)
            dev = self.bus.get(".UPower", dev_path)
            if dev.Type == 2:  # battery
                return {
                    "percentage": dev.Percentage,
                    "state": dev.State,
                    "charging": dev.State == 1,
                    "time_to_empty": dev.TimeToEmpty,  # seconds, 0 if unknown
                    "time_to_full": dev.TimeToFull,    # seconds, 0 if unknown
                }
        return None

    # --- Vibration ---
    # https://github.com/agx/feedbackd/blob/main/examples/example.py
    def set_vibration(self, enable: bool):
        # Connect to GSettings backend (org.gnome.SettingsDaemon, commonly)
        dconf = self.sess.get("org.sigxcpu.Feedback", "/org/sigxcpu/Feedback")

        # Use the standard Properties interface
        iface = dconf["org.sigxcpu.Feedback.Haptic"]

        # Example pattern: list of (duration, strength)
        pattern = [
            (3.0, 1),
            (1.0, 200),
            (0.0, 50),
            (0.5, 300),
        ]

        iface.Vibrate("org.foo.app", pattern)
        print(dir(iface))

    # --- Feedback: silent/full/... ---
    # broken
    def set_feedback_theme(self, value):
        # Connect to GSettings backend (org.gnome.SettingsDaemon, commonly)
        dconf = self.bus.get("org.gnome.SettingsDaemon", "/org/gnome/SettingsDaemon/Dbus")

        # Use the standard Properties interface
        iface = dconf["org.freedesktop.DBus.Properties"]

        # Set the key (schema, key, value)
        # GVariant format: value must match the expected type, here 's' = string
        value = Variant("s", "custom")

        iface.Set("org.sigxcpu.feedbackd", "theme", value)

    # --- Mobile network ---
    # Works as root
    def get_mobile_info(self):
        loc = None
        mm = self.bus.get("org.freedesktop.ModemManager1")
        for modem_path in mm.GetManagedObjects():
            modem = self.bus.get(".ModemManager1", modem_path)
            print("modem ", modem)
            operator = getattr(modem, "OperatorName", None)
            print("Operator code:", getattr(modem, "OperatorCode", None))  # 0..11 according to MMState
            print("State:", getattr(modem, "State", None))  # 0..11 according to MMState
            print("Access Technology:", getattr(modem, "AccessTechnologies", None))
            print("Model:", getattr(modem, "Model", None))
            print("Manufacturer:", getattr(modem, "Manufacturer", None))
            print("Revision:", getattr(modem, "Revision", None))
            print("Equipment Identifier (IMEI):", getattr(modem, "EquipmentIdentifier", None))

            print("Signal (gsm):", getattr(modem, "Gsm", None))
            print("Signal (umts):", getattr(modem, "Umts", None))
            print("Signal (lte):", getattr(modem, "Lte", None))

            print("Signal:", getattr(modem, "SignalQuality", None))
            print("RegistrationState:", getattr(modem, "RegistrationState", None))

            # Hallucination?
            lac = getattr(modem, "LocationAreaCode", None)
            cid = getattr(modem, "CellId", None)
            tac = getattr(modem, "TrackingAreaCode", None)
            print("Lac...:", lac, cid, tac)

            loc = getattr(modem, "Location", None)
            print("Location:", loc)

            v = modem.Setup(0x027, False)
            print("Location setup? ", v)
            v = modem.GetLocation()
            # This has 1) network info and 4) nmea
            print(v)

            # Fails with no signal; but has even timing-advance info (I guess only when transmitting)
            # It also seems to have neighbouring cells!
            """
            Field	Meaning	Example
            operator-id	MCC+MNC, identifies mobile operator	23003
            serving	Whether device is currently connected to this cell	True
            physical-ci	LTE Physical Cell ID (PCI)	12
            ci	LTE Cell Identity	XXXXXX
            tac	Tracking Area Code	XXXX
            earfcn	LTE frequency channel	XXXX
            cell-type	Cell type code (macro/micro/etc.)	5
            rsrp	Signal strength (dBm)	-122.7
            rsrq	Signal quality (dB)	-17.0
            """
            try: 
                v = modem.GetCellInfo()
            except:
                v = {}
            print(v)

            if False:
                simple = self.bus.get(".ModemManager1.Modem.Modem3gpp", modem_path)
                print(simple)

            if False:
                # --- Signal ---
                try:
                    modem3gpp = modem.Modem3gpp
                    if modem3gpp:
                        print("3GPP Operator Code:", getattr(modem3gpp, "OperatorCode", None))
                        print("Signal Quality:", getattr(modem3gpp, "SignalQuality", None))  # (percent, valid)
                        print("Registration State:", getattr(modem3gpp, "RegistrationState", None))
                except Exception:
                    print("No 3gpp?")

                # Pokud je LTE/other, ModemManager má ještě Modem4g nebo ModemSignal
                try:
                    signal = modem.Signal
                    if signal:
                        # SignalQuality může být tuple (percent, valid)
                        print("SignalQuality (Signal interface):", getattr(signal, "SignalQuality", None))
                except Exception:
                    print("No signal?")

            signal = None
            if False:
                try:
                    signal = modem.Signal.Get()["rssi"]
                except Exception as e:
                    return {"error": str(e)}
            return {"operator": operator, "signal_strength": signal}
        return loc

    def get_mobile_loc(self):
        loc = None
        mm = self.bus.get("org.freedesktop.ModemManager1")
        for modem_path in mm.GetManagedObjects():
            modem = self.bus.get(".ModemManager1", modem_path)
            loc = modem.GetLocation()
        return loc

    def get_cell_signal(self):
        loc = None
        mm = self.bus.get("org.freedesktop.ModemManager1")
        for modem_path in mm.GetManagedObjects():
            modem = self.bus.get(".ModemManager1", modem_path)

            loc = {}

            def attr(v):
                loc[v] = getattr(modem, v, None)
            
            attr("OperatorName")
            attr("OperatorCode")  # 0..11 according to MMState
            attr("State")  # 0..11 according to MMState
            attr("AccessTechnologies")
            attr("Model")
            attr("Manufacturer")
            attr("Revision")
            attr("EquipmentIdentifier")

            attr("Gsm")
            attr("Umts")
            attr("Lte")

            attr("SignalQuality")
            attr("RegistrationState")
            
        return loc

    def start_call(self, num):
        mm = self.bus.get("org.freedesktop.ModemManager1")

        for modem_path in mm.GetManagedObjects():
            modem = self.bus.get("org.freedesktop.ModemManager1", modem_path)
            voice = modem["org.freedesktop.ModemManager1.Modem.Voice"]

            call_properties = {
                "number": Variant('s', num)
            }

            call_path = voice.CreateCall(call_properties)
            #call = self.bus.get("org.freedesktop.ModemManager1", call_path)
            #call_iface = call["org.freedesktop.ModemManager1.Call"]
            #call_iface.Start()

            return { "call": call_path }

    def send_sms(self, num, text):
        mm = self.bus.get("org.freedesktop.ModemManager1")

        for modem_path in mm.GetManagedObjects():
            modem = self.bus.get("org.freedesktop.ModemManager1", modem_path)
            messaging = modem["org.freedesktop.ModemManager1.Modem.Messaging"]

            sms_properties = {
                "number": Variant('s', num),
                "text": Variant('s', text)
            }

            sms_path = messaging.Create(sms_properties)
            sms = self.bus.get("org.freedesktop.ModemManager1", sms_path)
            sms_iface = sms["org.freedesktop.ModemManager1.Sms"]
            sms_iface.Send()

            return { "sms": sms_path }

    # 0x01 = 3GPP LAC/CI
    # 0x02 = GPS NMEA
    # 0x04 = GPS RAW
    # 0x08 = CDMA BS
    # 0x10 = GPS Unmanaged
    CELL_ID  = 0x01
    GPS_NMEA = 0x02
    GPS_RAW  = 0x04

    def enable_mobile_loc(self, gps_on, cell_on):
        """
        Enable GPS RAW + NMEA.
        """
        mm = self.bus.get("org.freedesktop.ModemManager1")
        for modem_path in mm.GetManagedObjects():
            modem = self.bus.get(".ModemManager1", modem_path)

            # Setup(uint32 sources, boolean signal_location)
            # signal_location=True makes ModemManager emit LocationUpdated signals
            if gps_on:
                sources = self.GPS_NMEA | self.GPS_RAW
            else:
                sources = 0
            if cell_on:
                sources |= self.CELL_ID;
            modem.Setup(sources, True)

            continue
            # Optional: explicitly enable (some modems require it)
            try:
                modem.SetEnable(True)
            except Exception:
                print("Cant setenable")
                return { 'result' : 'setenable failed' }
        return { 'result': 'ok' }

    # --- WiFi ---
    def get_wifi_info(self):
        nm = self.bus.get("org.freedesktop.NetworkManager")
        wifi_enabled = nm.WirelessEnabled
        active_ssid = None
        for conn_path in nm.ActiveConnections:
            ac = self.bus.get(".NetworkManager", conn_path)
            if ac.Type == "802-11-wireless":
                # Step 1: get the settings connection path
                settings_path = ac.Connection
                # Step 2: fetch the settings object
                sc = self.bus.get(".NetworkManager", settings_path)
                settings = sc.GetSettings()
                ssid = settings["802-11-wireless"]["ssid"]
                if isinstance(ssid, (bytes, bytearray)):
                    ssid = ssid.decode("utf-8", errors="ignore")
                else:
                    ssid = ''.join(chr(c) for c in ssid)
                return {"enabled": nm.WirelessEnabled, "ssid": ssid}

        return {"enabled": wifi_enabled, "ssid": active_ssid}

    # --- Silent mode / Do Not Disturb ---
    # broken
    def get_silent_mode(self):
        try:
            portal = self.bus.get("org.freedesktop.portal.Desktop",
                                  "/org/freedesktop/portal/desktop")
            return portal.Settings.Read("org.freedesktop.appearance",
                                        "sound-theme-enabled") == 0
        except Exception as e:
            return {"error": str(e)}

    # --- Pending notifications ---
    # broken
    def get_notifications(self):
        try:
            notif = self.bus.get("org.freedesktop.Notifications")
            # org.freedesktop.Notifications has no standard "list" API,
            # Phosh implements its own.
            # In phosh, you can query /org/gnome/Notifications for backlog.
            phosh_notif = self.bus.get("org.gnome.Shell",
                                       "/org/gnome/Shell/Notifications")
            return phosh_notif.ListNotifications()
        except Exception as e:
            return {"error": str(e)}

    # --- GPS coordinates ---
    # Needs permissions from .desktop
    def get_location(self):
        try:
            geoclue = self.bus.get("org.freedesktop.GeoClue2",
                                   "/org/freedesktop/GeoClue2/Manager")
            # Step 1: get a client object path
            client_path = geoclue.GetClient()
            client = self.bus.get("org.freedesktop.GeoClue2", client_path)

            # Step 2: set required properties
            client.DesktopId = "phone.py"
            client.RequestedAccuracyLevel = 3  # 3 = city-level accuracy
            client.Start()  # start location updates

            # Step 3: read location
            loc_path = client.Location
            location = self.bus.get("org.freedesktop.GeoClue2", loc_path)

            return {
                "latitude": location.Latitude,
                "longitude": location.Longitude,
                "accuracy": location.Accuracy,
            }
        except Exception as e:
            return {"error": str(e)}

    # --- Hardware sensors (accelerometer, gyroscope, light, proximity) ---
    def get_hardware_sensors(self):
        try:
            obj = self.bus.get("net.hadess.SensorProxy", "/net/hadess/SensorProxy")

            # obj exposes multiple interfaces; access the one we need
            sensor_proxy = obj["net.hadess.SensorProxy"]

            # Enable accelerometer
            sensor_proxy.ClaimAccelerometer()
            sensor_proxy.ClaimLight()
            sensor_proxy.ClaimProximity()

            # Give it a small delay to start updating
            time.sleep(0.5)

            sensors = {}
            #print(dir(sensor_proxy))
            print('tilt -- tells you phone position -- ', sensor_proxy.AccelerometerTilt)
            print('orient -- orientation for screen rotation -- ', sensor_proxy.AccelerometerOrientation)
            
            # Ambient light
            if sensor_proxy.HasAmbientLight:
                sensors['ambient_light'] = {
                    'lux': sensor_proxy.LightLevel
                }

            # Proximity
            if sensor_proxy.HasProximity:
                sensors['proximity'] = {
                    'near': sensor_proxy.ProximityNear
                }

            return sensors
        except Exception as e:
            return {"error": str(e)}

    # --- Screen lock ---
    def get_screen_lock(self):
        # This one complains 
        #screensaver = self.sess.get("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver")
        screensaver = self.sess.get("org.gnome.ScreenSaver", "/org/gnome/ScreenSaver")
        print(dir(screensaver))
        #screensaver.SetActive(True)
        return { "Locked": screensaver.GetActive() }


# bus = SystemBus()
# login1 = bus.get("org.freedesktop.login1", "/org/freedesktop/login1")
# login1.Suspend(False)  # False = interactive, True = force
# login1.Hibernate(False)

phone = Phone()

def handle_cmd(v, a):
    if v == "bat":
        print(json.dumps(phone.get_battery_info()))
        sys.exit(0)
    if v == "loc":
        print(json.dumps(phone.get_mobile_loc()))
        sys.exit(0)
    if v == "loc_on":
        print(json.dumps(phone.enable_mobile_loc(True, True)))
        sys.exit(0)
    if v == "loc_off":
        print(json.dumps(phone.enable_mobile_loc(False, False)))
        sys.exit(0)
    if v == "signal":
        print(json.dumps(phone.get_cell_signal()))
        sys.exit(0)
    if v == "call":
        print(json.dumps(phone.start_call(a[2])))
        sys.exit(0)
    if v == "sms":
        print(json.dumps(phone.send_sms(a[2], a[3])))
        sys.exit(0)
    print("Unknown command "+v)
    sys.exit(1)

if len(sys.argv) > 1:
    handle_cmd(sys.argv[1], sys.argv)

def full():
    phone.init_sess()
    print("Battery:", phone.get_battery_info())
    phone.set_vibration(True)
#    print("Mobile:", phone.get_mobile_info())
    print("WiFi:", phone.get_wifi_info())
#    print("Silent mode:", phone.get_silent_mode())
#    print("Notifications:", phone.get_notifications())
    print("Location:", phone.get_location())
    print("Hardware sensors:", phone.get_hardware_sensors())
    print("Screen lock:", phone.get_screen_lock())
    phone.set_vibration(False)
    # full, quiet, silent
#    phone.set_feedback_theme("full")

def as_root():
    print("Battery:", phone.get_battery_info())
    print("Mobile:", phone.get_mobile_info())
    print("WiFi:", phone.get_wifi_info())
#    print("Silent mode:", phone.get_silent_mode())
#    print("Notifications:", phone.get_notifications())
#    print("Location:", phone.get_location())
    print("Hardware sensors:", phone.get_hardware_sensors())
    # full, quiet, silent
#    phone.set_feedback_theme("full")

#full()
as_root()
