#!/bin/sh

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")

indir="$1"
outdir="$2"
if [ -z "$indir" -o -z "$outdir" ]; then
	echo "Usage: $0 <inputdir> <outdir>"
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
		echo "Compiling $pyfile"
		#"$mydir"/../lvgl_micropython/lib/micropython/mpy-cross/build/mpy-cross -s "" "$pyfile"
		# -march= is needed to fix @viper stuff, but host is probably wrong because the host is x64 while it's running on esp32 (xtensawin)
		# this is fine for builtin/apps because they don't use viper, but lib/mpos/ does (audio) so that might not work
		"$mydir"/../lvgl_micropython/lib/micropython/mpy-cross/build/mpy-cross -s "" -march=host "$pyfile"
		#"$mydir"/../lvgl_micropython/lib/micropython/mpy-cross/build/mpy-cross -s "" -march=xtensawin "$pyfile"
		#"$mydir"/../lvgl_micropython/lib/micropython/mpy-cross/build/mpy-cross -s "" -march=x64 "$pyfile"
		result=$?
		if [ $result -ne 0 ]; then
			echo "error: $result"
			exit 2
		fi
	fi
	#echo "Removing it from the target folder..."
	rm "$pyfile"
done

