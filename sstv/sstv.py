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


def decode(in_path, out_path, sr, wave, encoding, mode, intro):
    iformat = out_path.split('.')[-1].upper()
    assert iformat in ['JPEG', 'JPG', 'BMP', 'PNG']

    logger.info(f'Using input parameters: sr={sr} wave={wave} encoding={encoding} mode={mode} intro={intro}')
    logger.info(f'Using output parameters: format={iformat}')

    f = open(out_path, 'wb')
    try:
        e = DECODERS['General'](f, encoding, mode, sr)
    except AssertionError:
        logger.error(f'Unknown encoder or mode provided!')
        sys.exit(1)

    if wave:
        e.read_wav(in_path)
    
    ns,freqs = e.process_pcm_samples()

    if e.slen - ns < 1000:
        print('No signal found!')
        sys.exit(1)

    header_size = round(sr*0.3)*2 + round(sr*0.01)
    if intro:
        header_size += round(sr*0.1)*8

    vis_size = round(sr*0.03)*10

    print(ns, header_size, vis_size)
    for val in freqs:
        print(val)

    return

    if encoding != 'FAX':
        e.decode_VIS()
    else:
        e.decode_phasing_interval()

    # lines = e.decode_image(template, recording)

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
    mode = None
    sr = 44100
    wav = True
    intro = False
    get_size = False
    for arg in args:
        if arg in ['--encode', '--decode']:
            func = arg
            in_path = args[args.index(arg)+1]
        elif arg == '--out':
            out_path = args[args.index(arg)+1]
        elif arg == '--encoding':
            encoding = args[args.index(arg)+1]
        elif arg == '--mode':
            mode = args[args.index(arg)+1]
        elif arg == '--sr':
            sr = int(args[args.index(arg)+1])
        elif arg == '--raw':
            wav = False
        elif arg == '--vox':
            intro = True
        elif arg == '--get_size':
            get_size = True

    # convert tool helper: print chosen encoding image size as WxH 
    if get_size and encoding and mode:
        if encoding in ENCODERS and mode in ENCODERS[encoding].opts:
            em = ENCODERS[encoding].opts[mode]
            print(f"{em['width']}x{em['height']}")
        
        sys.exit(1)

    if in_path and out_path:
        if func == '--encode' and encoding and mode:
            logger.info(f'Encoding {in_path}...')
            if encode(in_path, out_path, encoding, mode, intro, sr, wav):
                logger.info(f'Wrote output to {out_path}')

        elif func == '--decode':
            logger.info(f'Decoding {in_path}...')
            if decode(in_path, out_path, sr, wav, encoding, mode, intro):
                logger.info(f'Wrote output to {out_path}')

    logger.info('Done.')
