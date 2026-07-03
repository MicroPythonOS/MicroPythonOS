
dir="$1"
if [ -z "$dir" ]; then
	#dir="internal_filesystem/"
	echo "Usage: $0 dir/"
	exit 1
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
