#!/usr/bin/env python3
from struct import unpack, calcsize
import sys
import os

def main (args):
	if len (args) < 3:
		print (f'Feed me an image and offset to ISO9660 FS')
		return

	#Root directory offset in first volume descriptor
	ROOT = 156
	#Start of ISO9660 FS
	offset = int (args[2])

	def read_dir (f):
		base = f.tell ()
		size = unpack ('b', f.read (1))[0]
		f.seek (base + 2)
		lba = 2048*(unpack ('<I', f.read (4))[0] - 11716)
		f.seek (base + 10)
		length = unpack ('<I', f.read (4))[0]
		f.seek (base + 25)
		flags = unpack ('b', f.read (1))[0]
		f.seek (base + 32)
		name_length = unpack ('b', f.read (1))[0]
		name = f.read (name_length).decode ('latin')
		return size, lba, length, name_length, name, flags

	with open (args[1], 'rb') as f:
		f.seek (offset + ROOT)
		size, lba, length, name_length, name, flags = read_dir (f)
		print (f'{size} {lba} {length} {name_length} {name}')

		pathes = []
		visited = []
		dirs = [('ROOT', lba, 0)]
		while len (dirs):
			tup = dirs.pop ()

			dn = tup[0]
			pos = tup[1]
			depth = tup[2]

			f.seek (offset + pos)
			visited.append (pos)

			pathes = pathes[:depth]
			pathes.append (dn)
			joined = os.path.join (*pathes)
			os.makedirs (joined, exist_ok=True)

			print (depth*'  ' + f'{dn}')
			while True:
				base = f.tell ()
				size, lba, length, name_length, name, flags = read_dir (f)
				
				#Unsure of how to actually detect end of directory
				#but this seems to work... for now
				if 0 == size:
					break

				#Fix name up
				if ';' in name:
					name = name.split (';')[0]

				#Append directories to travel list or list item
				if flags&0x2:
					if lba in visited:
						continue
					dirs.append ((name, lba, depth + 1))
				else:
					#Dump file from image
					print (depth*'  ' + f'  {name} : {lba} {length}')
					with open (os.path.join (joined, name), 'wb') as d:
						f.seek (offset + lba)
						d.write (f.read (length))

				#Advance to next record in the directory
				f.seek (base + size)

			
				
if __name__ == "__main__":
	main (sys.argv)
