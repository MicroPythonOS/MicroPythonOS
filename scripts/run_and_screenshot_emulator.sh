# Somehow, the last line isn't parsed...
rm screenshot.png
rm /tmp/core.*
pkill -f qemu-system-xtensa
date
~/projects/MicroPythonOS/claude/qemu_a159x36/run.sh 2>&1 | while read line; do
	echo "$line"
	#if echo "$line" | grep -q "Starting asyncio REPL"; then
	if echo "$line" | grep -q "asyncio REPL task"; then
		echo "finished boot!" # this doesnt show
		sleep 1 # allow time for top menu bar to animate into view
		echo "making screenshot"
		import -window "$(xdotool getwindowfocus)" screenshot.png
		sleep 1
		echo "screenshot is in:"
		readlink -f screenshot.png
		echo "stopping emulator..."
		pkill -f qemu-system-xtensa
		echo "finished!"
		date
		echo "breaking..."
		echo "really breaking..."
		break
	fi
done
result=$?
echo "before exit"
date
echo "exit code: $result"

