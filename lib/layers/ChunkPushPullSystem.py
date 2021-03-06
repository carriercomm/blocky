import lib.layers.interface
import struct
import random
import time

from lib.ClientExceptions import *

class ChunkPushPullSystem(lib.layers.interface.ChunkSystem):
	ChunkFree 		= 1
	ChunkBegin		= 2
	ChunkData		= 3
	
	def GetBasePageSize(self):
		return self.base
	
	def GetLevelCount(self):
		return self.levels
	
	def __init__(self, client, load = True):
		self.client = client

		self.client.catchwrite = None
		
		if load:
			Load()
		else:
			self.levels = 28
			self.base = 4096
			self.bucketmaxslots = int((self.base - 10) / 8)
	
	def Load(self):
		levels, doffset, base = struct.unpack('>IQQ', client.Read(100, 4 + 8 * 2))
		self.levels = levels
		self.base = base
		self.doffset = doffset
	
	'''
		@sdescription:	Will return True if the block has been formatted for this system.
	'''
	def IsFormatted(self):
		client = self.client
		
		seg = client.Read(0, 8)
		
		if seg == b'cppscpps':
			return True
		return False
	
	'''
		@sdescription:	Will format the chunk using the specified base size. (WARNING: base size changing
		@+:				is not support at the moment)
	'''
	def Format(self, csize = 4096):
		client = self.client
	
		sig = client.Read(0, 8)
		# lets clear the signature field
		client.Write(0, bytes((0, 0, 0, 0, 0, 0, 0, 0)))
		# get block size
		bsz = client.GetBlockSize()
				
		levels = self.levels
		
		print('max storage size:%s' % ((4096 << (levels - 1)) * 510))
		
		#levelsize = 4096 << level
		
		# reserve 4096 bytes for the initial level stack for each and 4096 bytes for the master area
		doffset = 4096 * levels + 4096
		self.doffset = doffset
		
		# save this in the header
		client.Write(100, struct.pack('>IQQ', levels, doffset, self.base))
		
		# max 510 entries per bucket
		for levelndx in range(0, levels):
			# [next][top]
			client.Write(levelndx * 4096 + 4096, struct.pack('>QH', 0, 0))
			client.Write(200 + levelndx * 8, struct.pack('>Q', levelndx * 4096 + 4096))
		
		# work down creating the largest possible chunks
		# while placing the chunks into their respective
		# buckets; i am starting with 1GB so that makes
		# the maximum memory that i can manage 510GB, if
		# i start with a larger size (more levels) or increase
		# the smallest level i can handle larger blocks
		fsz = 4096 << (levels - 1)
		# subtract everything before the data offset (because it is used)
		_bsz = bsz - doffset
		clevel = levels - 1
		cmoff = doffset
		
		# make sure we do not go smaller than 4096 and that
		# we have at least 4096 bytes left.. we just discard
		# any extra at the end below 4096
		while fsz >= 4096 and _bsz >= 4096:
			# calculate whole chunks
			wgb = int(_bsz / fsz)
			# calculate remaining bytes
			_bsz = _bsz - (wgb * fsz)
			print('level:%s got %x count of %x size chunks with %x remaining' % (clevel, wgb, fsz, _bsz))
			# place chunks into bucket
			boff = 4096 + clevel * 4096
			# make sure we do not exceed the bucket's current limit; this
			# is likely to happen if we use too small of our largest buckets
			# size compared with the block size.. for example if our largest
			# bucket is 1GB and we have 512GB then we are likely going to
			# exceed 510 entries thus overfilling our boot strapping buckets
			assert(wgb <= 510)
			
			client.Write(boff, struct.pack('>QH', 0, wgb))
			
			for i in range(0, wgb):
				client.Write(boff + (8 + 2) + i * 8, struct.pack('>Q',  cmoff))
				print('cmoff:%x' % cmoff)
				# track our current data position in the block
				cmoff = cmoff + fsz
			# decrease chunk size
			fsz = fsz >> 1
			clevel = clevel - 1
	
		client.Write(0, b'cppscpps')
		return

	def UnitTest(self):
		client = self.client
	
		tpb = 0
		tpbc = 0
		lsz = 0
		
		client.SetVectorExecutedWarningLimit(2048)		
		segments = []
		while True:
			# let the network do anything it needs to do
			if client.GetOutstandingCount() >= 100:
				while client.GetOutstandingCount() >= 100:
					client.HandlePackets()
		
			sz = random.randint(1, 1024 * 1024 * 100)
			
			st = time.time()
			chunks = self.AllocChunksForSegment(sz)
			tt = time.time() - st
			
			tpb = tpb + (tt / (sz / 1024 / 1024 / 1024))
			tpbc = tpbc + 1
			
			print('avg-time-GB:%s large-alloc:%s this-time:%s' % (tpb / tpbc, lsz, tt))
			
			#print(chunks)
			
			if chunks is None:
				# free something
				st = time.time()
				if len(segments) < 1:
					continue
				#exit()
				i = random.randint(0, len(segments) - 1)
				for chunk in segments[i]:
					self.PushChunk(chunk[2], chunk[0])
				
				del segments[i]
				tt = time.time() - st
				# try to allocate again, and if fails
				# then we will free another
				continue
			if sz > lsz:
				lsz = sz
			
			# make sure no overlap
			for chunk in chunks:
				for segment in segments:
					for _chunk in segment:
						s = chunk[0]
						_s = _chunk[0]
						e = (chunk[0] + chunk[1])
						_e = (_chunk[0] + _chunk[1])
						if (s >= _s and s <= _e) or \
						   (e >= _s and e <= _e) or \
						   (_s >= s and _s <= e) or \
						   (_e >= s and _e <= e):
							print('OVERLAP')
							print('start:%x end:%x length:%x level:%s' % (s, e, chunk[1], chunk[2]))
							print('start:%x end:%x length:%x level:%s' % (_s, _e, _chunk[1], _chunk[2]))
							exit()	
			segments.append(chunks)
		
		while True:
			client.HandlePackets()
		return
		
	'''
		@sdescription:		Will allocate a series of chunks of possibly varying sizes, which
		@+:					shall be a total length specified. The `initialsub` specifies how
		@+:					many bytes must be compensated for in the first chunk. The `repeatsub`
		@+:					specifies how many bytes are reserved in each chunk except the first
		@+:					chunk. These two parameters are used to reserve space for one master
		@+:					header and subsequent headers for each chunk other than the first.
	'''
	def AllocChunksForSegment(self, seglength, initialsub = 0, repeatsub = 0):
		client = self.client
		while True:
			try:
				client.TransactionStart()
				chunks = []
				if self.__AllocChunksForSegment(seglength, self.levels - 1, chunks, initialsub = initialsub, repeatsub = repeatsub) is False:
					# push all the chunks we did get back..
					for chunk in chunks:
						# push chunk back into specified level
						self.PushChunk(chunk[2], chunk[0], nonewtrans = True)
					client.TransactionCommit()
					return None
				# we should have enough chunks for the segment
				client.TransactionCommit()
				return chunks
			except LinkDropException:
				print('LINKDROP')
				client.TransactionDrop()
				continue
			break
		
	def __AllocChunksForSegment(self, seglength, level, chunks, initialsub, repeatsub):
		if level < 0:
			#print('level bottomed out')
			return False
		# see if this size chunk will fit it
		lchunksz = self.base << level
		# if level is 0 then we will just have to have some waste because
		# there is no real way around it
		if lchunksz > seglength and level > 0:
			# too large, so try a lower level
			#print('level:%s is too large (lchunksz:%x seglength:%x) so going lower' % (level, lchunksz, seglength))
			return self.__AllocChunksForSegment(seglength, level - 1, chunks, initialsub, repeatsub)
		# how many can fit into it?
		cnt = int(seglength / lchunksz)
		if level == 0 and (cnt * lchunksz < seglength):
			# we are into base pages so we are going to have to just make
			# it work by partially using another page
			cnt = cnt + 1
		# try to allocate them
		for x in range(0, cnt):
			chunk = self.PullChunk(level, nonewtrans = True)
			if chunk is None:
				#print('none left in level:%s so going lower' % level)
				# no chunks left, try lower level
				return self.__AllocChunksForSegment(seglength, level - 1, chunks, initialsub, repeatsub)
			if len(chunks) < 1:
				# for the very first chunk subtract an initial value (used for accounting for header space)
				seglength = seglength - (lchunksz - initialsub)
			else:
				# for any other than first subtract a repeat value (used for accounting for header space)
				seglength = seglength - (lchunksz - repeatsub)
			chunks.append((chunk, lchunksz, level))
			if seglength < 1:
				return True
		# if we still have some left, try the next lower level
		return self.__AllocChunksForSegment(seglength, level - 1, chunks, initialsub, repeatsub)
	
	def __PushBasePages(self, pages):
		for page in pages:
			self.__PushBasePage(page)
		return True
	
	def __PushBasePage(self, page):
		client = self.client
		
		level = 0
		boff = struct.unpack('>Q', client.Read(200 + level * 8, 8))[0]
		next, top = struct.unpack('>QH', client.Read(boff, 10))
		if top == self.bucketmaxslots:
			# create new bucket from one of the pages
			time.sleep(2)
			client.Write(page, struct.pack('>QH', boff, 0))
			client.Write(200 + level * 8, struct.pack('>Q', page))
			return True
		# push a page into the bucket
		client.Write(boff + 10 + top * 8, struct.pack('>Q', page))
		client.Write(boff, struct.pack('>QH', next, top + 1))
		return True
	
	'''
		@sdescription:		Will push a chunk into the correct level based on it's size.
	'''
	def PushChunkBySize(self, sz, chunk):
		level = (sz / self.base) - 1
		return self.PushChunk(level, chunk)
	
	'''
		@sdescription:		Will push a chunk into the specified level.
	'''
	def PushChunk(self, level, chunk, nonewtrans = False):
		while True:
			try:
				client = self.client
				if nonewtrans is False:
					client.TransactionStart()
				# short-circuit to the specialized function for pages (not chunks)
				#print('push-chunk level:%s chunk:%x' % (level, chunk))
				if level == 0:
					res = self.__PushBasePage(chunk)
					if nonewtrans is False:
						client.TransactionCommit()
					return res
				boff = struct.unpack('>Q', client.Read(int(200 + level * 8), 8))[0]
				next, top = struct.unpack('>QH', client.Read(boff, 10))
				if top == self.bucketmaxslots:
					# create new bucket from ... a page (base page / base chunk)
					page = self.PullChunk(0, nonewtrans = True)
					if page is None:
						if nonewtrans is False:
							client.TransactionCommit()
						return False
					client.Write(page, struct.pack('>QH', boff, 0))
					client.Write(200 + level * 8, struct.pack('>Q', page))
					next = boff
					boff = page
					top = 0
					
				# push chunk into bucket
				client.Write(boff + 10 + top * 8, struct.pack('>Q', chunk))
				client.Write(boff, struct.pack('>QH', next, top + 1))
				if nonewtrans is False:
					client.TransactionCommit()
			except LinkDropException as e:
				# just re-raise it like we never caught it
				if nonewtrans is True:
					raise e
				client.TransactionDrop()
				continue
			break
		
	def __FillLevelOnce(self, level):
		if level + 1 >= self.levels:
			return False
		chunk = self.PullChunk(level + 1, nonewtrans = True)
		if chunk is None:
			# try to fill this level
			return False
		# okay we have a chunk from the upper level, now
		# lets split it and place it into this level
		#print('broke chunk %x size:%x into %x and %x of size %x' % (chunk, self.base << (level + 1), chunk, chunk + (self.base << level), self.base << level))
		self.PushChunk(level, chunk + (self.base << level), nonewtrans = True)
		self.PushChunk(level, chunk, nonewtrans = True)
		return True
	
	'''
		@sdescription:	Will pull a chunk from the specified level.
	'''
	def PullChunk(self, level = 0, nonewtrans = False):
		slackpages = []
		
		if nonewtrans:
			ret = self.__PullChunk(level, slackpages)
			self.__PushBasePages(slackpages)
			return ret
		
		while True:
			try:
				self.client.TransactionStart()
				ret = self.__PullChunk(level, slackpages)
				self.client.TransactionCommit()
			except LinkDropException:
				self.client.TransactionDrop()
				continue
			break
		while True:
			try:
				self.client.TransactionStart()
				self.__PushBasePages(slackpages)
				self.client.TransactionCommit()
			except LinkDropException:
				self.client.TransactionDrop()
				continue
			break
		return ret
		
	def __PullChunk(self, level, slackpages):
		client = self.client
		boff = struct.unpack('>Q', client.Read(200 + level * 8, 8))[0]
		next, top = struct.unpack('>QH', client.Read(boff, 10))
		if top == 0:
			#print('		bucket for level empty')
			# drop this page and get next
			if next == 0:
				# if we have to go any higher we are out of memory
				if level + 1 >= self.levels:
					return None
				# lets try to fill it with some pages
				if self.__FillLevelOnce(level) is False:
					#print('			filling level was fale')
					return None
				return self.__PullChunk(level, slackpages)
			client.Write(200 + level * 8, struct.pack('>Q', next))
			# store this unused base sized page
			slackpages.append(boff)
			# try again..
			return self.__PullChunk(level, slackpages)
			
		chunk = struct.unpack('>Q', client.Read(boff + 10 + (top - 1) * 8, 8))[0]
		client.Write(boff, struct.pack('>QH', next, top - 1))
		return chunk
	
	'''
		@sdescription:	Will get the client associated with this layer.
	'''
	def GetClient(self):
		return self.client