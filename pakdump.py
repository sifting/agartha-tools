#!/usr/bin/env python3
from struct import unpack, calcsize
import png
import sys
import os

def verify (cond, msg):
	if not cond:
		raise Exception (msg)

def pvr_decode (data):
	#Some PVR constants
	HEADER_SIZE = 16
	CODEBOOK_SIZE = 2048
	MAX_WIDTH = 0x8000
	MAX_HEIGHT = 0x8000
	
	#Image must be one of these
	ARGB1555 = 0x0
	RGB565   = 0x1
	ARGB4444 = 0x2
	YUV422   = 0x3
	BUMP     = 0x4
	PAL_4BPP = 0x5
	PAL_8BPP = 0x6
	
	#And one of these
	SQUARE_TWIDDLED            = 0x1
	SQUARE_TWIDDLED_MIPMAP     = 0x2
	VQ                         = 0x3
	VQ_MIPMAP                  = 0x4
	CLUT_TWIDDLED_8BIT         = 0x5
	CLUT_TWIDDLED_4BIT         = 0x6
	DIRECT_TWIDDLED_8BIT       = 0x7
	DIRECT_TWIDDLED_4BIT       = 0x8
	RECTANGLE                  = 0x9
	RECTANGULAR_STRIDE         = 0xB
	RECTANGULAR_TWIDDLED	   = 0xD
	SMALL_VQ                   = 0x10
	SMALL_VQ_MIPMAP            = 0x11
	SQUARE_TWIDDLED_MIPMAP_ALT = 0x12
	
	#For printing the above
	TYPES = [
		'ARGB1555',
		'RGB565',
		'ARGB4444',
		'YUV422',
		'BUMP',
		'4BPP',
		'8BPP'
	]
	FMTS = [
		'UNK0',
		'SQUARE TWIDDLED',
		'SQUARE TWIDDLED MIPMAP',
		'VQ',
		'VQ MIPMAP',
		'CLUT TWIDDLED 8BIT',
		'CLUT TWIDDLED 4BIT',
		'DIRECT TWIDDLED 8BIT',
		'DIRECT TWIDDLED 4BIT',
		'RECTANGLE',
		'UNK1',
		'RECTANGULAR STRIDE',
		'UNK2',
		'RECTANGULAR TWIDDLED',
		'UNK3',
		'UNK4',
		'SMALL VQ',
		'SMALL VQ MIPMAP',
		'SQUARE TWIDDLED MIPMAP ALT'
	]
	
	#Ensure the texture is PVR encoded
	if data[:4].decode ('ASCII', 'ignore') != 'PVRT':
		return 'Not a PVR texture!', ''
	
	#Extract header
	total, px, fmt, unk, width, height = unpack ('<IBBHHH', data[4:HEADER_SIZE])
	
	data = data[:8 + total]

	#Print info and verify
	print (f'    Type: {TYPES[px]} {FMTS[fmt]}, Size: {width}x{height}')
	verify (width < MAX_WIDTH, f'width is {width}; must be < {MAX_WIDTH}')
	verify (height < MAX_HEIGHT, f'height is {height}; must be < {MAX_HEIGHT}')
	
	#This is my favourite black magic spell!
	#Interleaves x and y to produce a morton code
	#This trivialises decoding PVR images
	def morton (x, y):
		x = (x|(x<<8))&0x00ff00ff
		y = (y|(y<<8))&0x00ff00ff
		x = (x|(x<<4))&0x0f0f0f0f
		y = (y|(y<<4))&0x0f0f0f0f
		x = (x|(x<<2))&0x33333333
		y = (y|(y<<2))&0x33333333
		x = (x|(x<<1))&0x55555555	
		y = (y|(y<<1))&0x55555555
		return x|(y<<1)
	
	#Colour decoders...
	def unpack1555 (colour):
		a = int (255*((colour>>15)&31))
		r = int (255*((colour>>10)&31)/31.0)
		g = int (255*((colour>> 5)&31)/31.0)
		b = int (255*((colour    )&31)/31.0)
		return [r, g, b, a]
		
	def unpack4444 (colour):
		a = int (255*((colour>>12)&15)/15.0)
		r = int (255*((colour>> 8)&15)/15.0)
		g = int (255*((colour>> 4)&15)/15.0)
		b = int (255*((colour    )&15)/15.0)
		return [r, g, b, a]
	
	def unpack565 (colour):
		r = int (255*((colour>>11)&31)/31.0)
		g = int (255*((colour>> 5)&63)/63.0)
		b = int (255*((colour    )&31)/31.0)
		return [r, g, b]
	
	#Format decoders...
	#GOTCHA: PVR stores mipmaps from smallest to largest!
	def vq_decode (raw, decoder):
		pix = []
		
		#Extract the codebook
		tmp = raw[HEADER_SIZE:]
		book = unpack (f'<1024H', tmp[:CODEBOOK_SIZE])
		
		#Skip to the largest mipmap
		#NB: This also avoids another gotcha:
		#Between the codebook and the mipmap data is a padding byte
		#Since we only want the largest though, it doesn't affect us
		size = len (raw)
		base = width*height//4
		lut = raw[size - base : size]
		
		#The codebook is a 2x2 block of 16 bit pixels
		#This effectively halves the image dimensions
		#Each index of the data refers to a codebook entry
		for i in range (height//2):
			row0 = []
			row1 = []
			for j in range (width//2):
				entry = 4*lut[morton (i, j)]
				row0.extend (decoder (book[entry + 0]))
				row1.extend (decoder (book[entry + 1]))
				row0.extend (decoder (book[entry + 2]))
				row1.extend (decoder (book[entry + 3]))
			pix.append (row0)
			pix.append (row1)
		return pix
	
	def morton_decode (raw, decoder):
		pix = []
		
		#Skip to largest mipmap
		size = len (raw)
		base = width*height*2
		mip = raw[size - base : size]
		
		data = unpack (f'<{width*height}H', mip)
		for i in range (height):
			row = []
			for j in range (width):
				row.extend (decoder (data[morton (i, j)]))
			pix.append (row)
		return pix
	
	#From observation:
	#All textures 16 bit
	#All textures are either VQ'd or morton coded (twiddled)
	#So let's just save time and only implement those
	if ARGB1555 == px:
		if SQUARE_TWIDDLED == fmt or SQUARE_TWIDDLED_MIPMAP == fmt:
			return morton_decode (data, unpack1555), 'RGBA'
		elif VQ == fmt or VQ_MIPMAP == fmt:
			return vq_decode (data, unpack1555), 'RGBA'
	elif ARGB4444 == px:
		if SQUARE_TWIDDLED == fmt or SQUARE_TWIDDLED_MIPMAP == fmt:
			return morton_decode (data, unpack4444), 'RGBA'
		elif VQ == fmt or VQ_MIPMAP == fmt:
			return vq_decode (data, unpack4444), 'RGBA'
	elif RGB565 == px:
		if SQUARE_TWIDDLED == fmt or SQUARE_TWIDDLED_MIPMAP == fmt:
			return morton_decode (data, unpack565), 'RGB'
		elif VQ == fmt or VQ_MIPMAP == fmt:
			return vq_decode (data, unpack565), 'RGB'
	
	#Oh, well...
	return 'Unsupported encoding', ''
		
def uncompress (data, extra):
	SIZE = 4096
	MASK = SIZE - 1
	
	extra += 1
	ring = SIZE*[0]
	r = 0
	
	out = []
	pos = 0
	
	ctl = 0
	while pos < len (data):
		if 0 == (ctl&256):
			if pos >= len (data):
				break
			ctl = data[pos]
			ctl |= 0xff00
			pos += 1
		
		#If bit is set then next byte in payload is a literal,
		#else it is a 12 bit offset, 4 bit length pair into a 4k ring buffer
		if ctl&1:
			c = data[pos]
			out.append (c)
			ring[r&MASK] = c
			pos += 1
			r += 1
		else:
			if pos >= len (data):
				break
			b0 = data[pos + 0]
			b1 = data[pos + 1]
			word = (b1<<8)|b0
			base = (word>>4)&0xfff
			length = (word&0xf) + extra
			offset = r - (base + 1)
			
			for i in range (length):
				c = ring[(offset + i)&MASK]
				out.append (c)
				ring[r&MASK] = c
				r += 1
			
			pos += 2
		#Advance to the next bit
		ctl >>= 1
	
	return bytes (out)

def main (args):
	DEST = 'contents'
	
	#Check args
	if len (args) < 2:
		print ('Feed me a PAK/HQR')
		return
	
	#Load the manifest
	split = os.path.splitext (args[1])
	with open (split[0] + '.lst', 'rb') as f:
		count = 0
		lines = f.readlines ()
		
		#Build a list of files
		files = []
		for ln in lines:
			#Remove blanks and comments
			ln = ln.decode ('latin').strip ().lower ().replace ('\0', '').replace ('\\', '/')
			if len (ln) < 2:
				continue
			if '' == ln:
				continue
			if '#' == ln[:1]:
				continue
			#Insert the path into the list for later
			files.append (ln)
			count += 1
	
	#Build a path list...
	paths = []
	for p in files:
		if ':' in p:
			path = p[p.index (':') + 2:]
		else:
			path = p
		sanitised = os.path.normpath (path)
		paths.append (sanitised)
	
	#Extract files from archive...
	with open (args[1], 'rb') as f:
		offsets = unpack (f'<{count}I', f.read (calcsize (f'<{count}I')))
		for i in range (count):
			#Rebuild path on disk
			fn = os.path.basename (paths[i])
			dn = os.path.join (DEST, os.path.basename (args[1]), os.path.dirname (paths[i]))
			os.makedirs (dn, exist_ok = True)
			
			#Seek to find and read header
			f.seek (offsets[i])
			uncompressed, compressed, mode = unpack ('<IIH', f.read (calcsize ('<IIH')))
			
			#Read and uncompress contents as needed
			MODE_RAW = 0
			MODE_UNK = 1
			MODE_LZSS = 2
			
			rate = 100*compressed/uncompressed
			MODES = ['uncompressed', 'LZSS_ALT', 'LZSS']
			print (f'Uncompressing "{paths[i]}", ratio: {rate:.4}% ({MODES[mode]}) {uncompressed}')
			if MODE_RAW == mode:
				data = f.read (compressed)
			elif MODE_UNK == mode or MODE_LZSS == mode:
				data = uncompress (f.read (compressed), mode)
				verify (len (data) == uncompressed, f'"{paths[i]}" uncompressed to {len (data)} bytes, instead of {uncompressed}')
			else:
				raise Exception (f'Unknown compression mode {mode}')
				
			if '.pvr' in paths[i]:
				data = data[16:]
					
				ret, mode = pvr_decode (data)
				try:
					verify (str != type (ret), f'image "{paths[i]}" failed to decode: {ret}!')
					png.from_array (ret, mode).save (os.path.join (dn, fn) + '.png')
				except:
					#Dump the image for examination
					with open (os.path.join (dn, fn), 'wb') as out:
						out.write (data)
			else:	
				#Write it to disk and free data
				with open (os.path.join (dn, fn), 'wb') as out:
					out.write (data)
			
			del data	
				
if __name__ == "__main__":
	main (sys.argv)
