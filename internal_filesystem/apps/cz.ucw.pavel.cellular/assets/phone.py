#!/usr/bin/env python3
from pydbus import SystemBus, Variant
import pydbus
import time
import sys
import json

"""
Lets make it class Phone, one method would be reading battery information, one would be reading operator name / signal strength, one would be getting wifi enabled/disabled / AP name.

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

