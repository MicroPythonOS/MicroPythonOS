#!/bin/bash

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")
testdir="$mydir"
scriptdir=$(readlink -f "$mydir"/../scripts/)
fs="$mydir"/../internal_filesystem/
mpremote="$mydir"/../lvgl_micropython/lib/micropython/tools/mpremote/mpremote.py

# Parse arguments
ondevice=""
onetest=""

while [ $# -gt 0 ]; do
    case "$1" in
        --ondevice)
            ondevice="yes"
            ;;
        *)
            onetest="$1"
            ;;
    esac
    shift
done

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

	# Detect if this is a graphical test (filename contains "graphical")
	if echo "$file" | grep -q "graphical"; then
		echo "Detected graphical test - including boot and main files"
		is_graphical=1
		# Get absolute path to tests directory for imports
		tests_abs_path=$(readlink -f "$testdir")
	else
		is_graphical=0
	fi

	if [ -z "$ondevice" ]; then
		# Desktop execution
		if [ $is_graphical -eq 1 ]; then
			# Graphical test: include boot_unix.py and main.py
			"$binary" -X heapsize=8M -c "$(cat main.py) ; import mpos.main ; import mpos.apps; sys.path.append(\"$tests_abs_path\")
$(cat $file)
result = unittest.main() ; sys.exit(0 if result.wasSuccessful() else 1) "
            result=$?
		else
			# Regular test: no boot files
			"$binary" -X heapsize=8M -c "$(cat main.py)
$(cat $file)
result = unittest.main() ; sys.exit(0 if result.wasSuccessful() else 1) "
            result=$?
		fi
	else
		if [ ! -z "$ondevice" ]; then
			echo "Hack: reset the device to make sure no previous UnitTest classes have been registered..."
			"$mpremote" reset
			sleep 15
		fi

		echo "Device execution"
		# NOTE: On device, the OS is already running with boot.py and main.py executed,
		# so we don't need to (and shouldn't) re-run them. The system is already initialized.
		cleanname=$(echo "$file" | sed "s#/#_#g")
		testlog=/tmp/"$cleanname".log
		echo "$test logging to $testlog"
		if [ $is_graphical -eq 1 ]; then
			# Graphical test: system already initialized, just add test paths
			"$mpremote" exec "$(cat main.py) ; sys.path.append('tests')
$(cat $file)
result = unittest.main()
if result.wasSuccessful():
    print('TEST WAS A SUCCESS')
else:
    print('TEST WAS A FAILURE')
" | tee "$testlog"
		else
			# Regular test: no boot files
			"$mpremote" exec "$(cat main.py)
$(cat $file)
result = unittest.main()
if result.wasSuccessful():
    print('TEST WAS A SUCCESS')
else:
    print('TEST WAS A FAILURE')
" | tee "$testlog"
		fi
		grep -q "TEST WAS A SUCCESS" "$testlog"
		result=$?
	fi
	popd
	return "$result"
}

failed=0
ran=0

if [ -z "$onetest" ]; then
	echo "Usage: $0 [one_test_to_run.py] [--ondevice]"
	echo "Example: $0 tests/simple.py"
	echo "Example: $0 tests/simple.py --ondevice"
	echo "Example: $0 --ondevice"
	echo
	echo "If no test is specified: run all tests from $testdir on local machine."
	echo
	echo "The '--ondevice' flag will run the test(s) on a connected device using mpremote.py (should be on the PATH) over a serial connection."
	while read file; do
		one_test "$file"
		result=$?
		if [ $result -ne 0 ]; then
			echo -e "\n\n\nWARNING: test $file got error $result !!!\n\n\n"
			failed=$(expr $failed \+ 1)
			exit 1
		else
			ran=$(expr $ran \+ 1)
		fi
	done < <( find "$testdir" -iname "test_*.py" )
else
	echo "doing $onetest"
	one_test $(readlink -f "$onetest")
	[ $? -ne 0 ] && failed=1
fi


if [ $failed -ne 0 ]; then
        echo "ERROR: $failed of the $ran tests failed"
        exit 1
else
	echo "GOOD: none of the $ran tests failed"
	exit 0
fi

