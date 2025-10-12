#!/usr/bin/env python3

from PIL import Image
import sys
import wave
from encoder import *

# http://lionel.cordesses.free.fr/gpages/Cordesses.pdf
# https://web.archive.org/web/20241227121817/http://www.barberdsp.com/downloads/Dayton%20Paper.pdf


ENCODERS = {
    'Martin': MartinEncoder,
    'Scottie': ScottieEncoder,
    'Wrasse': WrasseEncoder,
    'Pasokon': PasokonEncoder,
    'FAX': FAXEncoder,
    'Robot': RobotEncoder,
    'PD': PDEncoder
}


def encode(img_path, out_path, encoding, mode, intro_tone, sr=44100, wav=True):
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


def decode(data, mode):
    pass


def print_help():
    print('[!] Usage:\n\t./sstv.py ...')
    print('\nAvailable encoders and modes:')
    for key in ENCODERS.keys():
        print(f'\t{key}: {", ".join(ENCODERS[key].opts.keys())}')

    print('\nAvailable decoders and modes:')
    print('\t...')


if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) < 2:
        print_help()
        sys.exit(1)

    func = None
    img_path = None
    out_path = None
    encoding = None
    mode = None
    sr = 44100
    wav = True
    intro = False
    for arg in args:
        if arg in ['--encode', '--decode']:
            func = arg
            img_path = args[args.index(arg)+1]
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


    if img_path and out_path and encoding and mode:
        if func == '--encode':
            print(f'[+] Encoding {img_path}...')
            encode(img_path, out_path, encoding, mode, intro, sr, wav)
            print(f'[+] Wrote output to {out_path}')

    print('Done.')

# ffmpeg -f s16le -ar 22050 -ac 1 -i test.pcm -f alsa default 
