import socket
import struct
import random
import timeit
import threading
import os
import hashlib
import time
from lib import pubcrypt

class SymCrypt:
	def __init__(self, key):
		self.xkey = key[0:len(key) >> 1]
		self.mkey = key[len(key) >> 1:]
		
	def __both(self, data):
		di = 0
		ki = 0
		key = self.xkey
		out = []
		while di < len(data):
			out.append(data[di] ^ key[ki])
			di = di + 1
			ki = ki + 1
			if ki >= len(key):
				ki = 0
		return bytes(out)
		
	def mix(self, data):
		data = bytearray(data)
	
		dl = len(data)
		key = self.mkey
		
		di = 0
		ki = 0
		while di < dl:
			b = data[di]
			
			kv = key[ki]
			if kv == 0:
				kv = 1
			tondx = (dl - 1) % kv
			
			data[di] = data[tondx]
			data[tondx] = b
			
			di = di + 1
			ki = ki + 1
			if ki >= len(key):
				ki = 0
		return bytes(data)
		
	def unmix(self,  data):
		data = bytearray(data)
		dl = len(data)
		key = self.mkey

		mix = []
		# generate the sequence so that
		# i can play it backwards
		di = 0
		ki = 0
		while di < dl:
			kv = key[ki]
			if kv == 0:
				kv = 1
			tondx = (dl - 1) % kv
			mix.append((di, tondx))
			di = di + 1
			ki = ki + 1
			if ki >= len(key):
				ki = 0

		ml = len(mix)
		mi = ml - 1
		
		while mi > -1:
			frmndx = mix[mi][0]
			tondx = mix[mi][1]
		
			a = data[tondx]
			b = data[frmndx]
			
			data[tondx] = b
			data[frmndx] = a
		
			mi = mi - 1
		return bytes(data)
			
	'''
		@sdescription:		This will encrypt the data using the specified
		@+:					key during creation of the SymCrypt class.
	'''
	def crypt(self, data):
		return self.mix(self.__both(data))
	'''
		@sdescription:		This will decrypt the data using the specified
		@+:					key during creation of the SymCrypt class.
	'''
	def decrypt(self, data):
		return self.__both(self.unmix(data))
	
class PktCodeClient:
	GetPublicKey 		= 0
	SetupEncryption		= 1
	EncryptedMessage	= 2
	BlockConnect		= 3
	Write				= 4
	Read				= 5
	Exchange8			= 6
	BlockLock			= 7
	BlockUnlock			= 8
	BlockSize			= 9
	WriteAddLoop		= 10
	WriteHold		 	= 11
	DoWriteHold			= 12
	GetWriteHoldCount	= 13
	FlushWriteHold	 	= 14
	Ack					= 15
	Copy				= 16
	BlockLockInit		= 17
		
class PktCodeServer:
	PublicKey			= 0
	EstablishLink		= 1
	EstablishLinkFail	= 2		# TODO: implement
	EncryptedMessage	= 3
	BlockConnectFailure	= 4
	BlockConnectSuccess	= 5
	NoLink				= 6
	WriteSuccess		= 7
	ReadSuccess			= 8
	Exchange8Success	= 9
	OperationFailure	= 10
	BlockUnlockSuccess	= 11
	BlockUnlockFailed	= 12
	LockFailedOverlap	= 13
	LockFailedMax		= 14
	LockSuccess			= 15
	BlockSizeReply		= 16
	GetWriteHoldCount 	= 17
	FlushWriteHold		= 18
	BlockLockFailed		= 19
	BlockLockSuccess	= 20
	
class IDGen:
	def __init__(self, size):
		self.size = size
		self.gened = {}
	'''
		Generates a unique ID (could have been used before)
	'''
	def gen(size):
		o = []
		x = 0
		while x < size:
			o.append(random.randint(0, 255))
			x = x + 1
		return bytes(o)
	# TODO: add method to remove uid from self.gened once link has been dropped
	def urem(self, uid):
		if uid in self.gened:
			del self.gened[uid]
	'''
		Generates a unique (not used before) ID
	'''
	def ugen(self):
		while True:
			uid = IDGen.gen(self.size)
			if uid not in self.gened:
				self.gened[uid] = True
				return uid

class VectorManEntry:
	def __init__(self, begin, end):
		self.begin = begin
		self.end = end
				
class VectorMan:
	def __init__(self):
		self.high = 100
		self.irange = []
		
	def Flush(self):
		# flush the irange, but keep our same
		# vectors that we have been using, and
		# just keep going since a vector is a
		# 64-bit value it should NEVER wrap any
		# time within the year at least, LOL
		self.irange = []
		
	def IsVectorGood(self, vector, max = None):
		irange = self.irange
		for ir in irange:
			if vector >= ir.begin and vector <= ir.end:
				return False
		# okay we have a problem we have too many ranges, and the reason
		# we watch this is because someone could DoS the server's memory
		# by filling up the irange table so now we have to make a decision
		# if this vector will add with a range then we allow it and if it
		# does not then we report it as a bad vector
		if max is not None and len(irange) > max:
			# if it can be added to a range that is great, but if not
			# then we just consider it a bad vector
			if self.TryAddingVectorToRange(vector) is False:
				return False
		# see if we can add it to a range and if not make
		# a new range
		if self.TryAddingVectorToRange(vector) is False:
			#print('ADDED VECTOR:%s TO IRANGE' % vector)
			irange.append(VectorManEntry(vector, vector))
		
		return True
	'''
		this function needs improvement so that we are not
		storing every single vector, but instead store some
		as a range to decrease memory usage, and search time
		when checking if vector is in list
		
		BUT, this is okay for now for testing...
		
		TODO: improve this situation
	'''
	def TryAddingVectorToRange(self, vector):
		irange = self.irange
		added = False
		# find range we can append onto
		_ir = None
		#print('trying to add vector:%s to ranges' % vector)
		for ir in irange:
			#print('		vector:%s ir.begin:%s ir.end:%s' % (vector, ir.begin, ir.end))
			if vector + 1 == ir.begin:
				ir.begin = ir.begin - 1
				_ir = ir
				added = True
				break
			if vector - 1 == ir.end:
				ir.end = ir.end + 1
				_ir = ir
				added = True
				break
		if added:
			# try to combine range we just added to with another
			for ir in irange:
				if _ir.end + 1 == ir.begin:
					ir.begin = _ir.begin
					irange.remove(_ir)
					break
				if _ir.begin - 1 == ir.end:
					ir.end = _ir.end
					irange.remove(_ir)
					break
			return True
		#print('			failed to add')
		return False
			
	def IsRangeTooMany(self, max):
		if len(self.irange) > max:
			return True
		return False
	
	def GetNewVector(self):
		vector = self.high
		self.high = vector + 1
		return vector
				
def BuildEncryptedMessage(link, data, vector = None):
	crypter = link['crypter']
	vman = link['vman']
	ulid = link['ulid']
	
	# get new vector unless provided already
	if vector is None:
		vector = vman.GetNewVector()
		#if vector == 129:
		#	raise Exception('CHECKIT')
	# add vector and data (to be hashed)	
	_vector = struct.pack('>Q', vector)
	data = _vector + data
	
	#if _vector == 1117:
	#	raise Exception('LOL')
	
	# hash vector and data
	m = hashlib.sha512()
	m.update(data)
	hash = m.digest()
	#hash = bytearray(64)
		
	# encrypt data (but not ulid and type code)
	data = hash + data
	
	data = crypter.crypt(data)
	
	# add together to make final packet form
	data = struct.pack('>B', PktCodeClient.EncryptedMessage) + ulid + data
	
	# return final form
	return (data, vector)
				
def ProcessRawSocketMessage(link, data):	
	# if not encrypted then just return message whole
	if data[0] != PktCodeClient.EncryptedMessage:
		print('NOT ENCRYPTED', data)
		return (False, data, None)
	
	crypter = link['crypter']
	vman = link['vman']
	ulid = link['ulid']
	
	# it is encrypted so we need to decrypt and verify it
	data = data[1:]
	# get unique link id
	_ulid = data[0:4]
	if _ulid != ulid:
		# apparently, not meant for us..
		print('@', end='')
		return (None, data, None)
	data = data[4:]
		
	# decrypt remaining message
	data = crypter.decrypt(data)
	
	# get hash
	hash = data[0:64]
	# hash remaining data so we can verify hash
	data = data[64:]
	
	m = hashlib.sha512()
	m.update(data)
	_hash = m.digest()
	if _hash != hash:
		# failed hash verification (ignore it)
		print('#', end='')
		return (False, data, None)
	# verify vector is valid
	vector = struct.unpack_from('>Q', data)[0]
	# return the actual data (which has now been decrypted and verified)
	return (True, data[8:], vector)




