#!/bin/bash
# Build the SSTV encoder for the browser app in ./wasm

cd "$(dirname "$0")" || exit 1

emcc -O3 --no-entry -sSTANDALONE_WASM -sALLOW_MEMORY_GROWTH -sERROR_ON_UNDEFINED_SYMBOLS=0 \
	./wasm/encoder.c -o ./wasm/encoder.wasm
