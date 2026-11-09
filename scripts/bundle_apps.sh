#!/bin/sh

# Usage:
#   scripts/bundle_apps.sh                              # rebuild every app and the whole index
#   scripts/bundle_apps.sh --app com.example.myapp      # rebuild only this app, merge the index
#   scripts/bundle_apps.sh --app a --app b              # several apps
#
# With --app only the named apps are packaged; every other entry in the
# existing ../apps/app_index.json is kept as-is. Use it for single-app
# releases so a local bundle cannot regenerate (and revert) unrelated entries.

output=../apps/
outputjson="$output"/app_index.json
output=$(readlink -f "$output")
outputjson=$(readlink -f "$outputjson")
app_store_base_url="${APPS_BASE_URL:-https://apps.micropythonos.com}"

selected=""
merge=0
while [ $# -gt 0 ]; do
    case "$1" in
        --app)
            if [ -z "${2:-}" ]; then
                echo "ERROR: --app needs an app fullname" >&2
                exit 1
            fi
            selected="$selected $2"
            shift 2
            ;;
        --app=*)
            selected="$selected ${1#--app=}"
            shift
            ;;
        -h|--help)
            sed -n '3,11p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

#mpks="$output"/mpks/
#icons="$output"/icons/

mkdir -p "$output"
#mkdir -p "$mpks"
#mkdir -p "$icons"

#rm "$output"/*.mpk
#rm "$output"/*.png

if [ -n "$selected" ]; then
    if [ ! -f "$outputjson" ]; then
        echo "ERROR: --app needs an existing $outputjson to merge into" >&2
        exit 1
    fi
    merge=1
    entries=$(mktemp)
    trap 'rm -f "$entries"' EXIT
    outjson="$entries"
    echo "Merging into $outputjson (unlisted apps keep their current entry)"
else
    rm -f "$outputjson"
    outjson="$outputjson"
fi

# These apps are for testing, or aren't ready yet:
blacklist="com.quasikili.quasidoodle" # com.quasikili.quasidoodle doesn't work on touch screen devices
blacklist="$blacklist com.micropythonos.errortest com.micropythonos.errortest_delayed com.micropythonos.errortest_resume" # intentional bad apps for testing
blacklist="$blacklist com.micropythonos.doom" # not ready yet
blacklist="$blacklist cz.ucw.pavel.calendar cz.ucw.pavel.cellular cz.ucw.pavel.compass cz.ucw.pavel.weather" # not ready yet

echo "[" | tee -a "$outjson"

# currently, this script doesn't purge unnecessary information from the manifests, such as activities

built=" "
#for apprepo in internal_filesystem/apps internal_filesystem/builtin/apps; do
for apprepo in internal_filesystem/apps; do
    echo "Listing apps in $apprepo"
    for appdir in $(ls -1 "$apprepo" | sort); do
        if [ -n "$selected" ]; then
            case " $selected " in
                *" $appdir "*) ;;
                *) continue ;;
            esac
        fi
        if echo "$blacklist" | grep "$appdir"; then
            if [ -n "$selected" ]; then
                echo "ERROR: $appdir is blacklisted and cannot be bundled" >&2
                exit 1
            fi
            echo "Skipping $appdir because it's in blacklist $blacklist"
        else
            echo "Bundling $apprepo/$appdir"
            appfullpath="$apprepo/$appdir"
            if [ ! -d "$appfullpath" ]; then
                echo "Skipping $appdir because it is not a valid directory (broken symlink?)"
                continue
            fi
            dirty=$(git -C "$appfullpath" status --porcelain -- . 2>/dev/null)
            if [ -n "$dirty" ]; then
                echo "WARNING: $appdir has uncommitted changes; this package will not match any release"
            fi
            if [ -f "$appfullpath/MANIFEST.JSON" ]; then
                manifest="$appfullpath/MANIFEST.JSON"
            else
                manifest="$appfullpath/META-INF/MANIFEST.JSON"
            fi
            version=$( jq -r '.version' "$manifest" )
            result=$?
            if [ $result -ne 0 ]; then
                echo "Failed to parse $manifest !"
                exit 1
            fi
            jq --arg appdir "$appdir" --arg version "$version" --arg base_url "$app_store_base_url" '. + {
                icon_url: ($base_url + "/apps/" + $appdir + "/icons/" + $appdir + "_" + $version + "_64x64.png"),
                download_url: ($base_url + "/apps/" + $appdir + "/mpks/" + $appdir + "_" + $version + ".mpk")
            }' "$manifest" | tee -a "$outjson"
            result=$?
            if [ $result -ne 0 ]; then
                echo "Failed to enrich $manifest !"
                exit 1
            fi
            echo -n "," | tee -a "$outjson"
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
            if [ -f "$appfullpath/icon_64x64.png" ]; then
                icon_src="$appfullpath/icon_64x64.png"
            else
                icon_src="$appfullpath/res/mipmap-mdpi/icon_64x64.png"
            fi
            cp "$icon_src" "$thisappdir"/icons/"$appdir"_"$version"_64x64.png
            built="$built$appdir "
        fi
    done
done

# remove the last , to have valid json:

truncate -s -1 "$outjson"

echo "]" | tee -a "$outjson"

if [ "$merge" -eq 1 ]; then
    for appdir in $selected; do
        case "$built" in
            *" $appdir "*) ;;
            *)
                echo "ERROR: $appdir was not bundled (unknown app?)" >&2
                exit 1
                ;;
        esac
    done
    merged=$(mktemp)
    if ! jq --slurpfile new "$entries" -c '
        ($new[0] | map({key: .fullname, value: .}) | from_entries) as $by
        | (map(.fullname)) as $oldnames
        | (map(if $by[.fullname] then $by[.fullname] else . end)
           + [ $new[0][] | select(.fullname as $f | ($oldnames | index($f)) | not) ])
        | .[]
    ' "$outputjson" > "$merged"; then
        rm -f "$merged"
        echo "ERROR: failed to merge into $outputjson" >&2
        exit 1
    fi
    # Rewrite in the same layout the full bundle produces: one pretty-printed
    # object per entry, separated by ",\n" (keeps the diff to the bundled apps).
    newindex=$(mktemp)
    {
        echo "["
        first=1
        while IFS= read -r entry; do
            if [ "$first" -eq 0 ]; then
                printf ','
            fi
            first=0
            printf '%s\n' "$entry" | jq '.'
        done < "$merged"
        echo "]"
    } > "$newindex"
    rm -f "$merged"
    # mktemp creates 0600; the file is served by the web server, so make it
    # world-readable like the index it replaces.
    chmod 644 "$newindex"
    mv "$newindex" "$outputjson"
    echo "Updated $outputjson"
fi
