import ctypes


class Decoder():
    def __init__(self, f, wave=True, samp_rate=44100):
        self.file = f
        self.wav = wave
        self.sr = samp_rate

        self.load_libfft()


    def load_libfft(self):
        lib = ctypes.CDLL('../libfft.so')
        lib.fft.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_int]
        lib.fft.restype = None
        lib.ifft.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_int]
        lib.ifft.restype = None
        lib.dct.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_int]
        lib.dct.restype = None
        lib.hann.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_int]
        lib.hann.restype = None
        lib.filter.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_int]
        lib.filter.restype = None
        self.lib = lib
