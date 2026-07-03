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
	march="host"
	echo ""
	echo "************************************************************************"
	echo "WARNING: $0 defaulting to -march=$march."
	echo "         Pass -march <arch> when cross-compiling for embedded boards."
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

find -L "$outdir" -iname "*.py" | while read pyfile; do
	if [ -L "$pyfile" ]; then
		oldtarget=$(readlink -f "$pyfile")
		newtarget=$(echo "$oldtarget" | sed "s/.py\$/.mpy/g")
		newname=$(echo "$pyfile" | sed "s/.py\$/.mpy/g")
		echo "Symlinking $newname to $newtarget"
		ln -s "$newtarget" "$newname"
	else
		echo "Compiling $pyfile with -march=$march"
		"$mydir"/../lvgl_micropython/lib/micropython/mpy-cross/build/mpy-cross -s "" -O3 -march="$march" "$pyfile"
		result=$?
		if [ $result -ne 0 ]; then
			echo "error: $result"
			exit 2
		fi
	fi
	#echo "Removing it from the target folder..."
	rm "$pyfile"
done

