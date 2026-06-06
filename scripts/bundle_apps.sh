output=../apps/
outputjson="$output"/app_index.json
output=$(readlink -f "$output")
outputjson=$(readlink -f "$outputjson")
app_store_base_url="${APPS_BASE_URL:-https://apps.micropythonos.com}"

#mpks="$output"/mpks/
#icons="$output"/icons/

mkdir -p "$output"
#mkdir -p "$mpks"
#mkdir -p "$icons"

#rm "$output"/*.mpk
#rm "$output"/*.png
rm -f "$outputjson"

# These apps are for testing, or aren't ready yet:
# com.quasikili.quasidoodle doesn't work on touch screen devices AND has the wrong download URL
# com.micropythonos.errortest is an intentional bad app for testing (caught by tests/test_graphical_launch_all_apps.py)
# com.micropythonos.errortest_delayed is an intentional bad app for testing
# com.micropythonos.nostr isn't ready for release yet
blacklist="com.quasikili.quasidoodle com.micropythonos.nostr"
blacklist="$blacklist com.micropythonos.errortest com.micropythonos.errortest_delayed com.micropythonos.errortest_resume"
blacklist="$blacklist com.micropythonos.doom_launcher com.micropythonos.duke_launcher com.micropythonos.retrocore_launcher" # not ready yet
blacklist="$blacklist com.micropythonos.doom com.micropythonos.breakout" # not ready yet
blacklist="$blacklist cz.ucw.pavel.calendar cz.ucw.pavel.cellular cz.ucw.pavel.compass cz.ucw.pavel.weather" # not ready yet

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
            appfullpath="$apprepo/$appdir"
            manifest="$appfullpath/META-INF/MANIFEST.JSON"
            version=$( jq -r '.version' "$manifest" )
            result=$?
            if [ $result -ne 0 ]; then
                echo "Failed to parse $manifest !"
                exit 1
            fi
            jq --arg appdir "$appdir" --arg version "$version" --arg base_url "$app_store_base_url" '. + {
                icon_url: ($base_url + "/apps/" + $appdir + "/icons/" + $appdir + "_" + $version + "_64x64.png"),
                download_url: ($base_url + "/apps/" + $appdir + "/mpks/" + $appdir + "_" + $version + ".mpk")
            }' "$manifest" | tee -a "$outputjson"
            result=$?
            if [ $result -ne 0 ]; then
                echo "Failed to enrich $manifest !"
                exit 1
            fi
            echo -n "," | tee -a "$outputjson"
            thisappdir="$output"/apps/"$appdir"
            mkdir -p "$thisappdir"
            mkdir -p "$thisappdir"/mpks
            mkdir -p "$thisappdir"/icons
            mpkname="$thisappdir"/mpks/"$appdir"_"$version".mpk
            echo "Setting file modification times to a fixed value..."
            find -L "$appfullpath" -exec touch -t 202501010000.00 {} \;
            rm -f "$mpkname"
            echo "Creating $mpkname with deterministic file order..."
            (cd "$apprepo" && (find -L "$appdir" -type d; find -L "$appdir" -type f) | grep -v ".git/" | sort | TZ=CET zip -X -r0 "$mpkname" -@)
            cp "$appfullpath"/res/mipmap-mdpi/icon_64x64.png "$thisappdir"/icons/"$appdir"_"$version"_64x64.png
        fi
    done
done

# remove the last , to have valid json:

truncate -s -1 "$outputjson"

echo "]" | tee -a "$outputjson"
