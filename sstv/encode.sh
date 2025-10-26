#!/bin/bash


SOURCE=$1
OUT=$2
ENC=$3
MODE=$4

if [[ -z $SOURCE || -z $OUT || -z $ENC || -z $MODE ]]; then
	echo "Usage: ./encode.sh SOURCE TARGET ENCODING MODE"
	exit -1
fi

RESIZED="$SOURCE.tmp"

# Get required img size for chosen mode
SIZE=$(./sstv.py --get_size --encoding $ENC --mode $MODE)

if [[ -z $SIZE ]]; then
	echo "Invalid encoding or mode provided"
	exit -2
fi

# Re-size img and save to tmp file
magick $SOURCE -resize $SIZE\! $RESIZED

# Run encoder
./sstv.py --encode $RESIZED --encoding $ENC --mode $MODE --vox --out $OUT

# Cleanup
rm $RESIZED
