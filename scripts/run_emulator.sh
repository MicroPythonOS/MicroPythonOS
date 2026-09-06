rm screenshot.png
rm /tmp/core.*
pkill -f qemu-system-xtensa
date
logfile=/tmp/run_emulator.log
lines=0
maxlines=100
timeout=60
rm "$logfile"
timeout $timeout ~/projects/MicroPythonOS/claude/qemu_a159x36/run.sh 2>&1 | while read line; do
	echo "$line" >> "$logfile"
	lines=$(expr $lines \+ 1)
	if [ $lines -gt $maxlines ]; then
		echo "stopping after $maxlines lines"
		pkill -f qemu-system-xtensa
		break
	fi
	if false && echo "$line" | grep -q "asyncio REPL task"; then
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
result=$? # 124 means it had a timeout
echo -n "Emulator stopped at " ; date
if [ $result -eq 0 ]; then
	echo "Emulator stopped after reaching $maxlines"
elif [ $result -eq 124 ]; then
	echo "Emulator did not stop and had to be killed after timeout of $timeout seconds"
else
	echo "Emulator had different exit code: $result"
fi

