#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wave
import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)

from encoder import *
from decoder import *
from img import load_image

# http://lionel.cordesses.free.fr/gpages/Cordesses.pdf
# https://web.archive.org/web/20241227121817/http://www.barberdsp.com/downloads/Dayton%20Paper.pdf
# https://www.sstv-handbook.com/download/sstv-handbook.pdf


ENCODERS = {
    'Martin': MartinEncoder,
    'Scottie': ScottieEncoder,
    'Wrasse': WrasseEncoder,
    'Pasokon': PasokonEncoder,
    'FAX': FAXEncoder,
    'Robot': RobotEncoder,
    'PD': PDEncoder
}

DECODERS = {
    'General': Decoder
}


def encode(img_path, out_path, encoding, mode, intro_tone, sr, wav):
    assert encoding in ENCODERS

    if wav:
        f = wave.open(out_path, 'wb')
    else:
        f = open(out_path, 'wb')

    try:
        e = ENCODERS[encoding](f, wav, mode, sr)
    except AssertionError:
        logger.error(f'Unknown encoder or mode provided!')
        sys.exit(1)

    ext,w,h,data = load_image(img_path)

    ew,eh = e.enc['width'],e.enc['height']
    if (w,h) != (ew,eh):
        logger.warning(f'Error: input image dimensions ({w},{h}) not supported by encoding mode ({ew},{eh})')
        logger.warning('Please find a way to re-size your image')
        if w < ew or h < eh:
            logger.error('Stopping program execution')
            f.close()
            del data
            sys.exit(3)

    if intro_tone:
        e.generate_intro()

    e.generate_header()

    if encoding != 'FAX':
        e.generate_VIS()
    else:
        e.generate_phasing_interval()

    e.encode_image(data, ext)

    e.__del__()
    del data
    if not wav and not f.closed:
        f.close()

    return True


def decode(in_path, out_path, iformat, sr, wave, encoding, mode, intro):
    opath_ext = out_path.split('.')[-1]

    assert iformat in ['JPEG', 'JPG', 'BMP', 'PNG']

    if opath_ext != iformat:
        fixed_path = out_path.replace(f'.{opath_ext.lower()}', f'.{iformat.lower()}')
        if fixed_path.endswith('.tiff'):
            fixed_path = fixed_path[:-1]

        print(f'Your output path file extension [{opath_ext.upper()}] does not match the specified format [{iformat.upper()}]')
        choice = input(f'Would you like to change the output path to {fixed_path}? (Y/n) ')
        if not choice.lower() == 'n':
            out_path = fixed_path
            print(f'New output path: {out_path}')


    logger.info(f'Using input parameters: sr={sr} wave={wave} encoding={encoding} mode={mode} intro={intro}')
    logger.info(f'Using output parameters: format={iformat}')

    f = open(out_path, 'wb')
    try:
        e = DECODERS['General'](f, iformat, encoding, mode, sr)
    except AssertionError:
        logger.error(f'Unknown encoder or mode provided!')
        sys.exit(1)

    if wave:
        e.read_wav(in_path)
    
    fft_res = e.process_pcm_samples()

    # Create template sequence
    # NB! TODO count number of raw samples
    
    template = []
    if intro:
        template += [(1900,100),(1500,100),(1900,100),(1500,100),(2300,100),(1500,100),(2300,100),(1500,100)]

    if encoding != 'FAX':
        # Normal header
        template += [(1900,300), (1200,10), (1900,300)]
        # VIS
        template += [(1200, 30)]
        template += [(None, 30)]*8
        template += [(1200, 30)]
        # Parse VIS and verify encoding mode, check parity bit
        # Set up sync pulse timings to follow
    else:
        # FAX header
        template += [(2300,2.05), (1500,2.05)]*1220
        # phasing interval
        template += []

    # Martin M1
    for y in range(256):
        template += [(1200,4.862)]
        template += [(1500,0.572)]
        for j in range(3):
            for x in range(320):
                template += [(None,0.4576)]

            template += [(1500,0.572)]


    # Process samples and match
    recording = e.parse_samples(fft_res)

    e.decode_header()

    if encoding != 'FAX':
        e.decode_VIS()
    else:
        e.decode_phasing_interval()

    lines = e.decode_image(template, recording)

    e.__del__()
    if not wave and not f.closed:
        f.close()

    return False


def print_help():
    print('Usage:\n\t./sstv.py ...')
    print('\nAvailable encoders and modes:')
    for key in ENCODERS.keys():
        print(f'{" "*4}{key}:')
        for mode in ENCODERS[key].opts.keys():
            mm = ENCODERS[key].opts[mode]
            print(f'{" "*8}{mode} {mm["width"]}x{mm["height"]}')

    print('\nAvailable decoders and modes:')
    print('\t...')


if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) < 2:
        print_help()
        sys.exit(1)

    func = None
    in_path = None
    out_path = None
    encoding = None
    iformat = 'PNG'
    mode = None
    sr = 44100
    wav = True
    intro = False
    for arg in args:
        if arg in ['--encode', '--decode']:
            func = arg
            in_path = args[args.index(arg)+1]
        elif arg == '--out':
            out_path = args[args.index(arg)+1]
        elif arg == '--encoding':
            encoding = args[args.index(arg)+1]
        elif arg == '--format':
            iformat = args[args.index(arg)+1]
        elif arg == '--mode':
            mode = args[args.index(arg)+1]
        elif arg == '--sr':
            sr = int(args[args.index(arg)+1])
        elif arg == '--raw':
            wav = False
        elif arg == '--vox':
            intro = True


    if in_path and out_path:
        if func == '--encode' and encoding and mode:
            logger.info(f'Encoding {in_path}...')
            if encode(in_path, out_path, encoding, mode, intro, sr, wav):
                logger.info(f'Wrote output to {out_path}')

        elif func == '--decode':
            logger.info(f'Decoding {in_path}...')
            if decode(in_path, out_path, iformat, sr, wav, encoding, mode, intro):
                logger.info(f'Wrote output to {out_path}')

    logger.info('Done.')
