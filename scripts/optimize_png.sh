#find -iname "*.png" | while read file; do echo "$file" ;  ~/software/zopfli/zopflipng --iterations=500 --filters=01234mepb --lossy_8bit --lossy_transparent -y "$file" "$file" ; done

cd internal_filesystem/

find -L . -iname "*.png" -print0 | while IFS= read -r -d '' file; do
	echo "$file"
	convert "$file" -strip "$file"
	optipng -o7 "$file"
	~/software/zopfli/zopflipng   --iterations=500 --filters=01234mepb --lossy_8bit --lossy_transparent -y "$file" "$file"
done
