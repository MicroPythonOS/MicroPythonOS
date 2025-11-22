mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")

pkill -f "python.*mpremote"

appname="$1"

echo "This script will install the important files from internal_filesystem/ on the device using mpremote.py"
echo
echo "Usage: $0 [appname]"
echo "Example: $0"
echo "Example: $0 com.micropythonos.about"

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

# boot.py is not copied because it can't be overridden anyway

# The issue is that this brings all the .git folders with it:
#$mpremote fs cp -r apps :/

$mpremote fs mkdir :/apps
$mpremote fs cp -r apps/com.micropythonos.* :/apps/
find apps/ -maxdepth 1 -type l | while read symlink; do
	echo "Handling symlink $symlink"
	$mpremote fs mkdir :/"$symlink"
	$mpremote fs cp -r "$symlink"/* :/"$symlink"/

done

#echo "Unmounting builtin/ so that it can be customized..." # not sure this is necessary
#$mpremote exec "import os ; os.umount('/builtin')"
$mpremote fs cp -r builtin :/
$mpremote fs cp -r lib :/

#$mpremote fs cp -r data :/
#$mpremote fs cp -r data/images :/data/

popd

# Install test infrastructure (for running ondevice tests)
echo "Installing test infrastructure..."
$mpremote fs mkdir :/tests
$mpremote fs mkdir :/tests/screenshots

if [ ! -z "$appname" ]; then
	echo "Not resetting so the installed app can be used immediately."
	$mpremote reset
fi
