before=$(date)
echo "Don't forget to run ./scripts/install.sh if you have local work that you want to deploy and test."
echo "And add --no-install-test-apps to skip installing apps that are needed for the tests, if already installed."
sleep 1
name=$(date +%Y%m%d%H%M%S)
time ./scripts/test_runner.py --relayport /dev/ttyUSB0 --reset --ondevice --usb-unbind --logserial /tmp/$name-test_on_device-serial.log $@ 2>&1  | tee /tmp/$name-test_on_device-console.log
echo -n "Started at $before until " ; date

