inputfile="$1"
if [ -z "$inputfile" ]; then
    echo "Usage: $0 inputfile"
    echo "Example: $0 camera_capture_1764503331_960x960_GRAY.raw"
    exit 1
fi

outputfile="$inputfile".png
echo "Converting $inputfile to $outputfile"

# For now it's pretty hard coded but the format could be extracted from the filename...
convert -size 960x960 -depth 8 gray:"$inputfile" "$outputfile"
convert -size 42x42 -depth 8 rgba:font_diag_42x42_nts_assets_openmoji-72x72-color_263A.png.raw font_diag_42x42_nts_assets_openmoji-72x72-color_263A.png.raw.png
