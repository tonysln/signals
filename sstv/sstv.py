#!/usr/bin/env python3

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import wave

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)

from decoder import *
from encoder import *
from img import LD, SV, load_image, save_image

# http://lionel.cordesses.free.fr/gpages/Cordesses.pdf
# https://web.archive.org/web/20241227121817/http://www.barberdsp.com/downloads/Dayton%20Paper.pdf
# https://www.sstv-handbook.com/download/sstv-handbook.pdf


ENCODERS = {
    "Martin": MartinEncoder,
    "Scottie": ScottieEncoder,
    "Wrasse": WrasseEncoder,
    "Pasokon": PasokonEncoder,
    "FAX": FAXEncoder,
    "Robot": RobotEncoder,
    "PD": PDEncoder,
}

DECODERS = {"General": Decoder}


def encode(img_path, out_path, encoding, mode, intro_tone, sr, wav):
    assert encoding in ENCODERS

    ext = img_path.replace(".tmp", "").split(".")[-1].lower()
    if ext not in LD:
        logger.error(f"Input image format is not supported: {ext.upper()} (supported: {', '.join(LD).upper()})")
        sys.exit(1)

    if wav:
        f = wave.open(out_path, "wb")
    else:
        f = open(out_path, "wb")

    try:
        e = ENCODERS[encoding](f, wav, mode, sr)
    except AssertionError:
        logger.error("Unknown encoder or mode provided!")
        sys.exit(1)

    ext, w, h, data = load_image(img_path)

    ew, eh = e.enc["width"], e.enc["height"]
    if (w, h) != (ew, eh):
        logger.warning(
            f"Error: input image dimensions ({w},{h}) not supported by encoding mode ({ew},{eh})"
        )
        logger.warning("Please find a way to re-size your image")
        if w < ew or h < eh:
            logger.error("Stopping program execution")
            f.close()
            del data
            sys.exit(3)

    if intro_tone:
        e.generate_intro()

    e.generate_header()

    if encoding != "FAX":
        e.generate_VIS()
    else:
        e.generate_phasing_interval()

    e.encode_image(data, ext)

    e.__del__()
    del data
    if not wav and not f.closed:
        f.close()

    return True


def decode(in_path, out_path, sr, wav, encoding, mode):
    iformat = out_path.split(".")[-1].upper()
    if iformat.lower() not in SV:
        logger.error(f"Output image format is not supported: {iformat} (supported: {', '.join(SV).upper()})")
        sys.exit(1)

    # The mode is read from the VIS code, unless encoding and mode are given
    e = None
    if encoding or mode:
        if encoding not in ENCODERS or mode not in ENCODERS[encoding].opts:
            logger.error("Unknown encoder or mode provided!")
            sys.exit(1)

        e = ENCODERS[encoding](mode=mode)

    d = DECODERS["General"]()

    try:
        if wav:
            d.read_wav(in_path)
        else:
            d.read_raw(in_path, sr)

        w, h, data = d.decode(e)
    except DecodeError as err:
        logger.error(err)
        sys.exit(2)

    save_image(out_path, w, h, data)

    return True


def print_help():
    print("Usage:\n\t./sstv.py ...")
    print("\nAvailable encoders and modes:")
    for key in ENCODERS.keys():
        print(f"{' ' * 4}{key}:")
        for mode in ENCODERS[key].opts.keys():
            mm = ENCODERS[key].opts[mode]
            print(f"{' ' * 8}{mode} {mm['width']}x{mm['height']}")

    print("\nAvailable decoders and modes:")
    print("\t...")

    print("\nSupported image formats:")
    print(f"{' ' * 4}Input (encoding): {', '.join(LD).upper()}")
    print(f"{' ' * 4}Output (decoding): {', '.join(SV).upper()}")


if __name__ == "__main__":
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
        if arg in ["--encode", "--decode"]:
            func = arg
            in_path = args[args.index(arg) + 1]
        elif arg == "--out":
            out_path = args[args.index(arg) + 1]
        elif arg == "--encoding":
            encoding = args[args.index(arg) + 1]
        elif arg == "--mode":
            mode = args[args.index(arg) + 1]
        elif arg == "--sr":
            sr = int(args[args.index(arg) + 1])
        elif arg == "--raw":
            wav = False
        elif arg == "--vox":
            intro = True
        elif arg == "--get_size":
            get_size = True

    # convert tool helper: print chosen encoding image size as WxH
    if get_size and encoding and mode:
        if encoding in ENCODERS and mode in ENCODERS[encoding].opts:
            em = ENCODERS[encoding].opts[mode]
            print(f"{em['width']}x{em['height']}")

        sys.exit(1)

    if in_path and out_path:
        if func == "--encode" and encoding and mode:
            logger.info(f"Encoding {in_path}...")
            if encode(in_path, out_path, encoding, mode, intro, sr, wav):
                logger.info(f"Wrote output to {out_path}")

        elif func == "--decode":
            logger.info(f"Decoding {in_path}...")
            if decode(in_path, out_path, sr, wav, encoding, mode):
                logger.info(f"Wrote output to {out_path}")

    logger.info("Done.")
