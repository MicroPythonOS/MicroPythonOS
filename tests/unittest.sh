#!/bin/bash

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")
testdir="$mydir"
scriptdir=$(readlink -f "$mydir"/../scripts/)
fs="$mydir"/../internal_filesystem/
onetest="$1"
ondevice="$2"


# print os and set binary
os_name=$(uname -s)
if [ "$os_name" = "Darwin" ]; then
        echo "Running on macOS"
        binary="$scriptdir"/../lvgl_micropython/build/lvgl_micropy_macOS
else
        # other cases can be added here
        echo "Running on $os_name"
        binary="$scriptdir"/../lvgl_micropython/build/lvgl_micropy_unix
fi

binary=$(readlink -f "$binary")
chmod +x "$binary"

one_test() {
	file="$1"
	if [ ! -f "$file" ]; then
		echo "ERROR: $file is not a regular, existing file!"
		exit 1
	fi
	pushd "$fs"
	echo "Testing $file"
	if [ -z "$ondevice" ]; then
		"$binary" -X heapsize=8M -c "import sys ; sys.path.append('lib')
$(cat $file)
result = unittest.main() ; sys.exit(0 if result.wasSuccessful() else 1) "
		result=$?
	else
		cleanname=$(echo "$file" | sed "s#/#_#g")
		testlog=/tmp/"$cleanname".log
		echo "$test logging to $testlog"
		mpremote.py exec "import sys ; sys.path.append('lib')
$(cat $file)
result = unittest.main()
if result.wasSuccessful():
    print('TEST WAS A SUCCESS')
else:
    print('TEST WAS A FAILURE')
" | tee "$testlog"
		grep "TEST WAS A SUCCESS" "$testlog"
		result=$?
	fi
	popd
	return "$result"
}

failed=0

if [ -z "$onetest" ]; then
	echo "Usage: $0 [one_test_to_run.py] [ondevice]"
	echo "Example: $0 tests/simple.py"
	echo "Example: $0 tests/simple.py ondevice"
	echo
	echo "If no test is specified: run all tests from $testdir on local machine."
	echo
	echo "The 'ondevice' argument will try to run the test on a connected device using mpremote.py (should be on the PATH) over a serial connection."
	while read file; do
		one_test "$file"
		result=$?
		if [ $result -ne 0 ]; then
			echo "test $file got error $result"
			failed=$(expr $failed \+ 1)
		fi

	done < <( find "$testdir" -iname "test_*.py" )
else
	one_test $(readlink -f "$onetest")
	[ $? -ne 0 ] && failed=1
fi


if [ $failed -ne 0 ]; then
        echo "ERROR: $failed .py files have failing unit tests"
        exit 1
else
	echo "GOOD: no .py files have failing unit tests"
	exit 0
fi

