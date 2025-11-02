#!/bin/bash
mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")
fs="$mydir"/../internal_filesystem/
cross="$mydir"/../lvgl_micropython/lib/micropython/mpy-cross/build/mpy-cross

failed=0
while read file; do
	"$cross" -march=x64 -o /dev/null  "$file"
	exitcode="$?"
	if [ $exitcode -ne 0 ]; then
		echo "$file got exitcode $exitcode"
		failed=$(expr $failed \+ 1)
	fi
done < <(find "$fs" -iname "*.py")

if [ $failed -ne 0 ]; then
	echo "ERROR: $failed .py files have syntax errors"
	exit 1
else
	echo "GOOD: no .py files have syntax errors"
	exit 0
fi
