find internal_filesystem/ -iname "*.pyc" -exec rm {} \;
find internal_filesystem/ -iname "__pycache__" -exec rmdir {} \;
