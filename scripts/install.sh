pkill -f "python.*mpremote"

appname="$1"

if [ -z "$appname" ]; then
	echo "Usage: $0 [appname]"
	echo "Example: $0"
	echo "Example: $0 launcher"
	echo "Example: $0 wificonf"
	echo "Example: $0 appstore"
	sleep 2
fi

mpremote=~/projects/MicroPythonOS/lvgl_micropython/lib/micropython/tools/mpremote/mpremote.py

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


#$mpremote fs cp boot.py :/boot.py
$mpremote fs cp boot_fri3d2024.py :/boot.py
$mpremote fs cp main.py :/main.py

#$mpremote fs cp main.py :/system/button.py
#$mpremote fs cp autorun.py :/autorun.py
#$mpremote fs cp -r system :/

$mpremote fs cp -r apps :/
$mpremote fs cp -r builtin :/
$mpremote fs cp -r lib :/
$mpremote fs cp -r resources :/

#$mpremote fs cp -r data :/
#$mpremote fs cp -r data/images :/data/

popd

$mpremote reset
