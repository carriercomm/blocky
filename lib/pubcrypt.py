import random
import math
import base64
import struct

def __gen_prime(N=10**8, bases=range(2,20000)):
    # XXX replace with a more sophisticated algorithm
    p = 1
    while any(pow(base, p-1, p) != 1 for base in bases):
        p = random.SystemRandom().randrange(N)
    return p

def __multinv(modulus, value):
    '''Multiplicative inverse in a given modulus

        >>> multinv(191, 138)
        18
        >>> 18 * 138 % 191
        1

    '''
    # http://en.wikipedia.org/wiki/Extended_Euclidean_algorithm
    x, lastx = 0, 1
    a, b = modulus, value
    while b:
        a, q, b = b, a // b, a % b
        x, lastx = lastx - q * x, x
    result = (1 - lastx * modulus) // value
    return result + modulus if result < 0 else result

def keygen(N):
    '''Generate public and private keys from primes up to N.

        >>> pubkey, privkey = keygen(2**64)
        >>> msg = 123456789012345
        >>> coded = pow(msg, 65537, pubkey)
        >>> plain = pow(coded, privkey, pubkey)
        >>> assert msg == plain

    '''
    # http://en.wikipedia.org/wiki/RSA
    prime1 = __gen_prime(N)
    prime2 = __gen_prime(N)
    totient = (prime1 - 1) * (prime2 - 1)
    return prime1 * prime2, __multinv(totient, 65537)

'''
	This function expects bytes not str.
'''
def toi256(data):
	t = 0
	n = 1
	for b in data:
		b = b
		t = t + (b * n)
		n = n * 256
	return t
	
def toi256r(data):
	t = 0
	n = 1
	i = len(data) - 1
	while i > -1:
		b = data[i]
		t = t + (b * n)
		n = n * 256
		i = i - 1
	return t

def fromi256(i):
	o = []
	m = 1
	while m < i:
		m = m * 256
	if m > i:
		m = divmod(m, 256)[0]
	while i > 0:
		r = divmod(i, m)[0]
		o.insert(0, r)
		i = i - (r * m)
		m = m >> 8
	return bytes(o)
	
def crypt(data, key):
	exp = toi256(key[0])
	pubkey = toi256(key[1])
	
	data = toi256(data)
	
	# value, exponent, modulus
	
	data = pow(data, exp, pubkey)
	return fromi256(data)
	
def decrypt(data, key):
	prikey = toi256(key[0])
	pubkey = toi256(key[1])
	
	data = toi256(data)
	data = pow(data, prikey, pubkey)
	return fromi256(data)
	
def readKeyFile(path):
	fd = open(path, 'r')
	lines = fd.readlines()
	fd.close()
	
	out = []
	for line in lines:
		line = line.strip()
		if line.find(':') < 0 and line.find('-') < 0:
			out.append(line)
	
	out = ''.join(out)
	
	return base64.b64decode(bytes(out, 'utf8'))

def readSSHPublicKey(path):
	# do not ask me.. had lots of trouble digging through openssh
	# source.. building it.. producing different results... LOL..
	# i just gave up and hacked this together
	fd = open(path, 'rb')
	data = fd.read()
	fd.close()
	data = data.split(b' ')
	data = data[1]
	
	data = base64.b64decode(data)
	
	sz = struct.unpack_from('>I', data)[0]
	data = data[4:]
	type = data[0:sz]
	data = data[sz:]
	
	sz = struct.unpack_from('>I', data)[0]
	data = data[4:]
	exp = data[0:sz]
	data = data[sz:]
	
	sz = struct.unpack_from('>I', data)[0]
	data = data[4:]
	mod = data[0:sz]
	
	return (exp, mod)
	
def readSSHPrivateKey(path):
	data = readKeyFile(path)
	
	fields = []
	
	data = data[4:]
	ndx = 0
	
	while len(data) > 0:
		type = data[0]
		data = data[1:]
		
		sz = data[0]
		data = data[1:]
		
		if sz == 0x82:
			sz = data[0] << 8 | data[1]
			data = data[2:]
		
		# create field
		field = (type, data[0:sz])
		# drop used data
		data = data[sz:]
		
		# add field
		fields.append(field) 
		fields[ndx] = field
		ndx = ndx + 1
		
	return (fields[3][1], fields[1][1])
	
'''
msg = 'hello'

pubkey, prikey = keygen(2**64)
print('pubkey:%s' % pubkey)
print('prikey:%s' % prikey)

coded = crypt(msg, pubkey)
plain = decrypt(coded, prikey, pubkey)
print(msg)
print(plain)
assert(msg == plain)
exit()
'''