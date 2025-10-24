import struct
import ctypes
from PIL import Image
from ctypes import c_char_p, c_int, POINTER, c_ubyte, byref, c_ulong


lib = ctypes.CDLL("../lib/libimg.so")
lib.load_png.argtypes = [c_char_p, POINTER(c_ubyte), POINTER(c_ulong), POINTER(c_ulong)]
lib.load_png.restype = c_int
lib.load_tiff.argtypes = [c_char_p, POINTER(c_ubyte), POINTER(c_ulong), POINTER(c_ulong)]
lib.load_tiff.restype = c_int
lib.load_bmp.argtypes = [c_char_p, POINTER(c_ubyte), POINTER(c_ulong), POINTER(c_ulong)]
lib.load_bmp.restype = c_int
lib.free_image.argtypes = [POINTER(c_ubyte)]
lib.free_image.restype = None


def load_BMP(path):
    return None


def load_PNG(path):
    buf = POINTER(c_ubyte)()
    w, h = c_ulong(), c_ulong()

    if lib.load_png(path.encode('utf-8'), buf, byref(w), byref(h)) != 0:
        raise RuntimeError("Failed to load PNG")

    size = w.value * h.value * 3
    data = ctypes.string_at(buf, size)
    print(f'[.] Detected PNG size: ({w.value},{h.value})')

    lib.free_image(buf)
    del buf
    return w.value, h.value, memoryview(data)


def load_TIFF(path):
    return None


def load_image(path):
    # img = Image.open(path).convert('RGB')
    # w,h = img.size
    # return w,h,memoryview(img.tobytes())

    ext = path.split('.')[-1].lower()

    if ext == 'bmp':
        return load_BMP(path)
    elif ext == 'png':
        return load_PNG(path)
    elif ext in ('tif', 'tiff'):
        return load_TIFF(path)
    else:
        print(f'[!] Error: provided image format is not supported: {ext.upper()}')
        raise ValueError('Unsupported image format')
