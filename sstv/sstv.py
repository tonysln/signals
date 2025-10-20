#!/usr/bin/env python3

from PIL import Image
import sys
import wave
from encoder import *
from decoder import *

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
        print(f'[!] Unknown encoder or mode provided!')
        sys.exit(1)

    img = Image.open(img_path).convert('RGB')

    w,h = e.enc['width'], e.enc['height']
    img = img.resize((w, h), Image.LANCZOS) # TODO handle
    # img.save('output.png')

    if intro_tone:
        e.generate_intro()

    e.generate_header()

    if encoding != 'FAX':
        e.generate_VIS()
    else:
        e.generate_phasing_interval()

    data = memoryview(img.tobytes())
    e.encode_image(data)

    e.__del__()
    if not wav and not f.closed:
        f.close()

    return True


def decode(in_path, out_path, iformat, sr, wave, encoding, mode, intro):
    print(f'[.] Using input parameters: sr={sr} wave={wave} encoding={encoding} mode={mode} intro={intro}')
    print(f'[.] Using output parameters: format={iformat}')

    assert iformat.upper() in ['TIFF', 'TIF', 'BMP', 'PNG']

    f = open(out_path, 'wb')
    try:
        e = DECODERS['General'](f, iformat, encoding, mode, sr)
    except AssertionError:
        print(f'[!] Unknown encoder or mode provided!')
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
    print('[!] Usage:\n\t./sstv.py ...')
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
            print(f'[+] Encoding {in_path}...')
            if encode(in_path, out_path, encoding, mode, intro, sr, wav):
                print(f'[+] Wrote output to {out_path}')

        elif func == '--decode':
            print(f'[+] Decoding {in_path}...')
            if decode(in_path, out_path, iformat, sr, wav, encoding, mode, intro):
                print(f'[+] Wrote output to {out_path}')

    print('Done.')
