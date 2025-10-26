#!/usr/bin/env python3

import sys
import logging
logger = logging.getLogger(__name__)


class FSKEncoder():
	def __init__(self):
		self.phase = 0.0
        self.clock = 0.0
        self.last_sample = 0
        self.SR = samp_rate
        self.A = 32767
        self.file = f

        logger.info(f'Using sample rate {self.SR} Hz')

        self.baud = 1200
        self.mark_hz = 1200
        self.space_hz = 2200


	def encode(self):
		pass



class FSKDecoder():
	def __init__(self):
		pass


	def decode(self):
		pass



if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) < 2:
        sys.exit(1)


    logger.info('Done.')
