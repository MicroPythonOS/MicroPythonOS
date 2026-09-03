#!/bin/sh

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")

march=""
while [ $# -gt 0 ]; do
	case "$1" in
		-march)
			march="$2"
			shift 2
			;;
		-march=*)
			march="${1#-march=}"
			shift
			;;
		*)
			break
			;;
esac
done

if [ -z "$march" ]; then
	echo ""
	echo "************************************************************************"
	echo "NOTE: $0 running without -march (bytecode only, no native emitter)."
	echo "      Pass -march <arch> when cross-compiling for embedded boards"
	echo "      or -march host for native desktop performance."
	echo "************************************************************************"
	echo ""
fi

indir="$1"
outdir="$2"
if [ -z "$indir" -o -z "$outdir" ]; then
	echo "Usage: $0 [-march <arch>] <inputdir> <outdir>"
	exit 1
fi

mkdir -p "$outdir"

# Follow symlinks so linked app directories are copied as real files.
cp -RL "$indir"/* "$outdir"

# Strip development junk that must never ship inside the firmware image:
# CPython __pycache__/.pyc (e.g. from a desktop `python3 -m py_compile` syntax
# check -- gitignored, so invisible in `git status`, but a single stray .pyc
# froze 64 KiB into local builds and looked like issue #268), macOS .DS_Store,
# and editor backup files.
find "$outdir" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find "$outdir" \( -name "*.pyc" -o -name ".DS_Store" -o -name "*.bak" -o -name "*~" \) -type f -delete

find -L "$outdir" -iname "*.py" | while read pyfile; do
	if [ -L "$pyfile" ]; then
		oldtarget=$(readlink -f "$pyfile")
		newtarget=$(echo "$oldtarget" | sed "s/.py\$/.mpy/g")
		newname=$(echo "$pyfile" | sed "s/.py\$/.mpy/g")
		echo "Symlinking $newname to $newtarget"
		ln -s "$newtarget" "$newname"
	else
		if [ -n "$march" ]; then
			echo "Compiling $pyfile with -march=$march"
			"$mydir"/../lvgl_micropython/lib/micropython/mpy-cross/build/mpy-cross -s "" -O3 -march="$march" "$pyfile"
		else
			echo "Compiling $pyfile (bytecode only)"
			"$mydir"/../lvgl_micropython/lib/micropython/mpy-cross/build/mpy-cross -s "" -O3 "$pyfile"
		fi
		result=$?
		if [ $result -ne 0 ]; then
			echo "error: $result"
			exit 2
		fi
	fi
	#echo "Removing it from the target folder..."
	rm "$pyfile"
done

