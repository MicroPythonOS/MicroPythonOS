mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")

pkill -f "python.*mpremote"

target="$1"
appname="$2"

if [ -z "$target" ]; then
	echo "Usage: $0 <target> [appname]"
	echo "Example: $0 fri3d-2024"
	echo "Example: $0 waveshare-esp32-s3-touch-lcd-2"
	echo "Example: $0 fri3d-2024 appstore"
	echo "Example: $0 waveshare-esp32-s3-touch-lcd-2 imu"
	exit 1
fi



mpremote=$(readlink -f "$mydir/../lvgl_micropython/lib/micropython/tools/mpremote/mpremote.py")

pushd internal_filesystem/

if [ ! -z "$appname" ]; then
	echo "Installing one app: $appname"
	appdir="apps/$appname/"
        target="apps/"
	if [ ! -d "$appdir" ]; then
		echo "$appdir doesn't exist so taking the builtin/"
		appdir="builtin/apps/$appname/"
                target="builtin/apps/"
		if [ ! -d "$appdir" ]; then
			echo "$appdir also doesn't exist, exiting..."
			exit 1
		fi
	fi
        $mpremote mkdir "/apps"
        $mpremote mkdir "/builtin"
        $mpremote mkdir "/builtin/apps"
	$mpremote fs cp -r "$appdir" :/"$target"
	echo "start_app(\"/$appdir\")"
	$mpremote
	popd
	exit
fi


#if [ -z "$target" -o "$target" == "waveshare-esp32-s3-touch-lcd-2" ]; then
#	$mpremote fs cp boot.py :/boot.py
#else
#	$mpremote fs cp boot_"$target".py :/boot.py
#fi
#$mpremote fs cp main.py :/main.py

#$mpremote fs cp main.py :/system/button.py
#$mpremote fs cp autorun.py :/autorun.py
#$mpremote fs cp -r system :/

# The issue is that this brings all the .git folders with it:
#$mpremote fs cp -r apps :/

$mpremote fs mkdir :/apps
$mpremote fs cp -r apps/com.micropythonos.* :/apps/
find apps/ -maxdepth 1 -type l | while read symlink; do
	echo "Handling symlink $symlink"
	$mpremote fs mkdir :/"$symlink"
	$mpremote fs cp -r "$symlink"/* :/"$symlink"/

done

$mpremote fs cp -r builtin :/
$mpremote fs cp -r lib :/
#$mpremote fs cp -r resources :/

#$mpremote fs cp -r data :/
#$mpremote fs cp -r data/images :/data/

popd

# Install test infrastructure (for running ondevice tests)
echo "Installing test infrastructure..."
$mpremote fs mkdir :/tests
$mpremote fs mkdir :/tests/screenshots
testdir=$(readlink -f "$mydir/../tests")
$mpremote fs cp "$testdir/graphical_test_helper.py" :/tests/graphical_test_helper.py

if [ -z "$appname" ]; then
	echo "Not resetting so the installed app can be used immediately."
	$mpremote reset
fi
