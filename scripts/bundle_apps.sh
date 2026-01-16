output=../apps/
outputjson="$output"/app_index.json
output=$(readlink -f "$output")
outputjson=$(readlink -f "$outputjson")

#mpks="$output"/mpks/
#icons="$output"/icons/

mkdir -p "$output"
#mkdir -p "$mpks"
#mkdir -p "$icons"

#rm "$output"/*.mpk
#rm "$output"/*.png
rm "$outputjson"

# These apps are for testing, or aren't ready yet:
# com.quasikili.quasidoodle doesn't work on touch screen devices
# com.micropythonos.filemanager doesn't do anything other than let you browse the filesystem, so it's confusing
# com.micropythonos.errortest is an intentional bad app for testing (caught by tests/test_graphical_launch_all_apps.py)
# com.micropythonos.showbattery is just a test
# com.micropythonos.doom_launcher isn't ready because the firmware doesn't have doom built-in yet
# com.micropythonos.nostr isn't ready for release yet
blacklist="com.micropythonos.filemanager com.quasikili.quasidoodle com.micropythonos.errortest com.micropythonos.showbattery com.micropythonos.doom_launcher"

echo "[" | tee -a "$outputjson"

# currently, this script doesn't purge unnecessary information from the manifests, such as activities

#for apprepo in internal_filesystem/apps internal_filesystem/builtin/apps; do
for apprepo in internal_filesystem/apps; do
    echo "Listing apps in $apprepo"
    ls -1 "$apprepo" | sort | while read appdir; do
	if echo "$blacklist" | grep "$appdir"; then
		echo "Skipping $appdir because it's in blacklist $blacklist"
	else
		echo "Bundling $apprepo/$appdir"
		pushd "$apprepo"/"$appdir"
		manifest=META-INF/MANIFEST.JSON
		version=$( jq -r '.version' "$manifest" )
		cat "$manifest" | tee -a "$outputjson"
		echo -n "," | tee -a "$outputjson"
		thisappdir="$output"/apps/"$appdir"
		mkdir -p "$thisappdir"
		mkdir -p "$thisappdir"/mpks
		mkdir -p "$thisappdir"/icons
		mpkname="$thisappdir"/mpks/"$appdir"_"$version".mpk
		echo "Setting file modification times to a fixed value..."
		find . -type f -exec touch -t 202501010000.00 {} \;
		echo "Creating $mpkname with deterministic file order..."
		find . -type f | grep -v ".git/" | sort | TZ=CET zip -X -r0 "$mpkname" -@
		cp res/mipmap-mdpi/icon_64x64.png "$thisappdir"/icons/"$appdir"_"$version"_64x64.png
		popd
	fi
    done
done

# remove the last , to have valid json:

truncate -s -1 "$outputjson"

echo "]" | tee -a "$outputjson"
