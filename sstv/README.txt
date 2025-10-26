SSTV Encoder & Decoder


Encoding
	Supported input image formats: PNG, JPEG, BMP.
	Supported output audio formats: WAV.

	Available encoders and modes:
	    Martin:
	        M1 320x256
	        M2 320x256
	        M3 320x128
	        M4 320x128
	    Scottie:
	        S1 320x256
	        S2 320x256
	        S3 320x128
	        S4 320x128
	        DX 320x256
	    Wrasse:
	        SC2-30 320x128
	        SC2-60 320x256
	        SC2-120 320x256
	        SC2-180 320x256
	    Pasokon:
	        P3 640x496
	        P5 640x496
	        P7 640x496
	    FAX:
	        FAX480 512x480
	    Robot:
	        36 320x240
	        72 320x240
	    PD:
	        PD50 320x256
	        PD90 320x256
	        PD120 640x496
	        PD160 512x400
	        PD180 640x496
	        PD240 640x496
	        PD290 800x616

	Important: source image size must be exact and compatible with the encoding mode.


Decoding
	Supported input audio formats: WAV.
	Supported output image formats: ...

	Under development!


Required tools and libraries
	Python
	GCC
	zlib
	libpng
	libjpeg


Optional tools
	ImageMagick


Usage
	If running for the first time, execute build.sh to generate libfft.so and libimg.so. 
	These simple libraries are used to read & write images and to run FFT on audio.
	
	Encode:
		./sstv.py --encode SOURCE --out TARGET --encoding ENCODING --mode MODE

		Alternatively, to auto-resize the source image (ImageMagick required):
			./encode.sh SOURCE TARGET ENCODING MODE

	Decode:
		./sstv.py --decode SOURCE --out TARGET --format IMG_FORMAT ...

	Optional arguments:
		--vox 
		...
