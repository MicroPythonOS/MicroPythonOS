dir="$1"
if [ -z "$dir" ]; then
	echo "Usage: $0 dir/ or file.png"
	exit 1
fi

if [ -f "$dir" ]; then
	file="$dir"
	ls -al "$file"
	echo =========
	~/software/pngquant --speed 1 --strip --ext .png --skip-if-larger --force "$file"
	result=$?
	echo "pngquant result is $result"
	ls -al "$file"
	~/software/zopfli/zopflipng   --iterations=50 --filters=01234mepb --lossy_8bit --lossy_transparent -y "$file" "$file"
	ls -al "$file"
	exit 0
fi

cd "$dir"

find -L . -iname "*.png" -print0 | while IFS= read -r -d '' file; do
	ls -al "$file"
	echo =========
	~/software/pngquant --speed 1 --strip --ext .png --skip-if-larger --force "$file"
	result=$?
	echo "pngquant result is $result"
	ls -al "$file"
	~/software/zopfli/zopflipng   --iterations=50 --filters=01234mepb --lossy_8bit --lossy_transparent -y "$file" "$file"
	ls -al "$file"
done
