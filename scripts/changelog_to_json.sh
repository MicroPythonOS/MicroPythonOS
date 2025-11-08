sed -i "s/\"/'/g" CHANGELOG.md # change double to single quotes
cat CHANGELOG.md | tr -d "\n" | sed 's/- /\\n- /g'
