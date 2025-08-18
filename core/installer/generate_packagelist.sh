#!/usr/bin/env bash

pip freeze --exclude-editable | grep -v "@ file://" > requirements.txt


set -e

echo "dependencies = ["

pip freeze --exclude-editable | grep -v "@ file://" | while read line; do
    pkg=$(echo "$line" | cut -d= -f1)
    ver=$(echo "$line" | cut -d= -f3)
    major=$(echo "$ver" | cut -d. -f1)
    next_major=$((major+1))
    echo "    \"${pkg}>=${ver},<${next_major}.0\","
done

echo "]"


