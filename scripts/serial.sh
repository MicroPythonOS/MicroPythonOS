#2024:
#tio /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_34:85:18:74:70:A0-if00
#tio /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_34:85:18:96:D3:30-if00
# Nobuzz:
#tio /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_34:85:18:AC:30:68-if00
# low brightness 2024:
#tio /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_34:85:18:AB:AF:1C-if00
# 2026:
#tio /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_DC:B4:D9:0B:7D:48-if00

# final badge with good buttons
#tio /dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_90:70:69:00:94:34-if00

device=$(find /dev/serial/by-id -iname "usb-Espressif_Systems_Espressif_Device*" | tail -n 1)

if [ -z "$device" ]; then
	echo "could not find device, defaulting to final badge 2026..."
        device=/dev/serial/by-id/usb-Espressif_Systems_Espressif_Device_9070690094340000-if00
fi

# After moving to usbip:
#tio -t /dev/serial/by-id/usb-Espressif_Systems_Espressif_Device_9070690094340000-if00

# Watch:
#tio -t /dev/serial/by-id/usb-Espressif_Systems_Espressif_Device_d0cf133336300000-if00

tio -t "$device"

