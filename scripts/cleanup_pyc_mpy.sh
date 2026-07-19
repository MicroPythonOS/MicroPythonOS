find internal_filesystem/ -iname "*.pyc" -exec rm {} \;
find internal_filesystem/ -iname "__pycache__" -exec rmdir {} \;
find internal_filesystem/ -iname "*.mpy" | grep -v breakout_ | while read file; do echo "deleting $file" ; rm "$file"; done
