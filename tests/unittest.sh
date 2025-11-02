#!/bin/bash

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")
testdir="$mydir"
scriptdir=$(readlink -f "$mydir"/../scripts/)
fs="$mydir"/../internal_filesystem/
onetest="$1"


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

one_test() {
	file="$1"
	pushd "$fs"
	echo "Testing $file"
	"$binary" -X heapsize=8M -c "import sys ; sys.path.append('lib') 
$(cat $file)
result = unittest.main() ; sys.exit(0 if result.wasSuccessful() else 1) "
	result=$?
	popd
	return "$result"
}

failed=0

if [ -z "$onetest" ]; then
	echo "Usage: $0 [one_test_to_run.py]"
	echo "Example: $0 tests/simple.py"
	echo
	echo "If no test is specified: run all tests from $testdir"
	while read file; do
		one_test "$file"
		result=$?
		if [ $result -ne 0 ]; then
			echo "test $file got error $result"
			failed=$(expr $failed \+ 1)
		fi

	done < <( find "$testdir" -iname "*.py" )
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

