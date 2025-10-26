import struct
import ctypes
from ctypes import c_char_p, c_int, POINTER, c_ubyte, byref, c_ulong, string_at, c_bool


lib = ctypes.CDLL("../lib/libimg.so")
lib.load_png.argtypes = [c_char_p, POINTER(POINTER(c_ubyte)), POINTER(c_ulong), POINTER(c_ulong)]
lib.load_png.restype = c_int
lib.load_bmp.argtypes = [c_char_p, POINTER(POINTER(c_ubyte)), POINTER(c_ulong), POINTER(c_ulong)]
lib.load_bmp.restype = c_int
lib.load_jpg.argtypes = [c_char_p, POINTER(POINTER(c_ubyte)), POINTER(c_ulong), POINTER(c_ulong)]
lib.load_jpg.restype = c_int
lib.free_image.argtypes = [POINTER(c_ubyte)]
lib.free_image.restype = None

LD = {
    'bmp': lib.load_bmp,
    'png': lib.load_png,
    'jpg': lib.load_jpg,
    'jpeg': lib.load_jpg
}


def load_image(path):
    ext = path.split('.')[-1].lower()

    if ext in LD:
        print(f'[+] Detected image format: {ext.upper()}')

        buf = POINTER(c_ubyte)()
        w, h = c_ulong(), c_ulong()

        res = LD[ext](path.encode('utf-8'), byref(buf), byref(w), byref(h))
        if res != 0:
            raise RuntimeError(f"Failed to load image: error code {res}")

        size = w.value * h.value * 3
        data = string_at(buf, size)
        # data = ctypes.memoryview_at(buf, size) nb! 3.14 feature
        print(f'[+] Detected image size: ({w.value},{h.value})')

        lib.free_image(buf)
        return (ext, w.value, h.value, memoryview(data))


    print(f'[!] Error: provided image format is not supported: {ext.upper()}')
    raise ValueError('Unsupported image format')
