#!/bin/bash

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")
testdir="$mydir"
scriptdir=$(readlink -f "$mydir"/../scripts/)
fs="$mydir"/../internal_filesystem/
heapsize=32M

# Parse arguments
ondevice=""
onetest=""
PORT="${MPOS_TEST_PORT:-/dev/ttyACM0}"

while [ $# -gt 0 ]; do
    case "$1" in
        --ondevice)
            ondevice="yes"
            ;;
        --port)
            shift
            PORT="$1"
            ondevice="yes"
            ;;
        *)
            onetest="$1"
            ;;
    esac
    shift
done

os_name=$(uname -s)
if [ "$os_name" = "Darwin" ]; then
        echo "Running on macOS"
        binary="$scriptdir"/../lvgl_micropython/build/lvgl_micropy_macOS
else
        echo "Running on $os_name"
        binary="$scriptdir"/../lvgl_micropython/build/lvgl_micropy_unix
fi

binary=$(readlink -f "$binary")
chmod +x "$binary"

rm -f "$scriptdir"/../internal_filesystem/prefs/com.micropythonos.settings/config.json

one_test() {
	file="$1"
	if [ ! -f "$file" ]; then
		echo "ERROR: $file is not a regular, existing file!"
		exit 1
	fi
	echo "Testing $file"

	tests_abs_path=$(readlink -f "$testdir")
	cleanname=$(echo "$file" | sed "s#/#_#g")
	testlog=/tmp/"$cleanname".log
	echo "logging to $testlog"

	max_attempts=3
	for attempt in $(seq 1 $max_attempts); do
		if [ $attempt -gt 1 ]; then
			echo "Retry attempt $attempt for $file"
		fi

		if [ -z "$ondevice" ]; then
			python3 "$scriptdir/unified_test_runner.py" \
				--backend process \
				--binary "$binary" \
				--heapsize "$heapsize" \
				--test-file "$file" \
				--tests-dir "$tests_abs_path" \
				| tee "$testlog"
			result=$?
		else
			python3 "$scriptdir/unified_test_runner.py" \
				--backend serial \
				--port "$PORT" \
				--test-file "$file" \
				--tests-dir "$tests_abs_path" \
				| tee "$testlog"
			result=$?
		fi

		if [ $result -eq 0 ]; then
			break
		fi
		if [ $result -lt 128 ]; then
			break
		fi
		echo "Test crashed with exit code $result — retrying..."
	done

	return "$result"
}

failed=0
ran=0

if [ -z "$onetest" ]; then
	echo "Usage: $0 [one_test_to_run.py] [--ondevice] [--port <port>]"
	echo "Example: $0 tests/simple.py"
	echo "Example: $0 tests/simple.py --ondevice"
	echo "Example: $0 tests/simple.py --ondevice --port /dev/pts/5"
	echo "Example: $0 --ondevice --port /dev/ttyACM0"
	echo "  MPOS_TEST_PORT env var sets default serial port (default: /dev/ttyACM0)"
	echo
	echo "If no test is specified: run all tests from $testdir on local machine."
	echo
	files=$(find "$testdir" -iname "test_*.py" )
	for file in $files; do
		one_test "$file"
		result=$?
		if [ $result -ne 0 ]; then
			echo -e "\n\n\nWARNING: test $file got error $result !!!\n\n\n"
			failed=$(expr $failed \+ 1)
			exit 1
		else
			ran=$(expr $ran \+ 1)
		fi
	done
else
	echo "doing $onetest"
	one_test $(readlink -f "$onetest")
	result=$?
	if [ $result -ne 0 ]; then
		echo "Test returned result: $result"
		failed=1
	fi
fi


if [ $failed -ne 0 ]; then
        echo "ERROR: $failed of the $ran tests failed"
        exit 1
else
	echo "GOOD: none of the $ran tests failed"
	exit 0
fi

