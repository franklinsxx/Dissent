"""
Filename: bulk_node.py
Description: The main class that implements the
shuffle+bulk anonymous data exchange protocol.
"""

import logging, random, sys, os, shutil
from time import sleep, time
from logging import debug, info, critical
from math import log, ceil
import cPickle, tempfile, struct, tarfile, base64

import M2Crypto.RSA
import M2Crypto.EVP

from utils import Utilities
from anon_crypto import AnonCrypto, AnonRandom
from anon_net import AnonNet
from shuffle_node import shuffle_node

class bulk_node():
	def __init__(self, id, key_len, round_id, n_nodes,
			my_addr, leader_addr, prev_addr, next_addr, msg_file):
		ip,port = my_addr

		self.id = id
		self.key_len = key_len
		self.n_nodes = n_nodes
		self.ip = ip
		self.port = int(port)
		self.round_id = round_id
		self.leader_addr = leader_addr
		self.prev_addr = prev_addr
		self.next_addr = next_addr
		self.phase = 0

		self.msg_file = msg_file

		self.start_time = time()

		info("Node started (id=%d, addr=%s:%d, key_len=%d, round_id=%d, n_nodes=%d)"
			% (id, ip, port, key_len, round_id, n_nodes))

		logger = logging.getLogger()
		h = logging.FileHandler("logs/node%04d.final" % self.id)
		h.setLevel(logging.CRITICAL)
		logger.addHandler(h)
		logger.setLevel(logging.DEBUG)

		self.pub_keys = {}

		'''
		if self.id > 0: sys.exit()
		# Use this to test crypto functions
		self.generate_keys()
		c = 's' * 1024 * 1024 * 100
		for i in xrange(0, 10):
			c = AnonCrypto.encrypt_with_rsa(self.key1, c)
			self.debug("len %d" % len(c))
		sys.exit()
		'''

	def run_protocol(self):
		self.run_phase0()
		self.run_phase1()
		self.run_phase2()
		self.run_phase3()
		self.run_phase4()
		self.critical("SUCCESSROUND:BULK,%d,%d,%g%s" % \
				(self.round_id, self.n_nodes, time() - self.start_time, self.size_string()))

	def size_string(self):
		c = ''
		for f in self.output_filenames():
			c = c + ",%d" % os.path.getsize(f)
		return c

	def output_filenames(self):
		return self.data_filenames

	def advance_phase(self):
		self.phase = self.phase + 1

	def am_leader(self):
		return self.id == 0
	
	def am_last(self):
		return self.id == (self.n_nodes - 1)

	"""
	PHASE 0

	Key exchange.  Since this is just a demo, we have all nodes
	send each other their primary and secondary public keys.  Of course
	in a real implementation, they should already have each other's
	primary public keys so that they can sign this first message.
	"""
		
	def run_phase0(self):
		self.advance_phase()
		self.public_keys = []
		self.generate_keys()

		if self.am_leader():
			self.debug('Leader starting phase 1')

			"""
			The leader needs to save addresses so that (s)he can
			broadcast to all nodes.
			"""
			(all_msgs, addrs) = self.recv_from_n(self.n_nodes-1)
			
			""" Get all node addrs via this msg """
			self.addrs = self.unpickle_pub_keys(all_msgs)

			if not self.have_all_keys():
				raise RuntimeError, "Missing public keys"
			self.info('Leader has all public keys')

			pick_keys_str = self.phase0b_msg()
			self.broadcast_to_all_nodes(pick_keys_str)
			self.info('Leader sent all public keys')

		else:
			self.send_to_leader(self.phase0_msg())
		
			""" Get all pub keys from leader """
			(keys, addrs) = self.recv_from_n(1)
			self.unpickle_keyset(keys[0])

			self.info('Got keys from leader!')

	def unpickle_keyset(self, keys):
		"""
		Method that non-leader nodes use to unpack all 
		public keys from the leader's message.
		"""
		(rem_round_id, keydict) = cPickle.loads(keys)

		if rem_round_id != self.round_id:
			raise RuntimeError, "Mismatched round ids"

		for i in keydict:
			s1,s2 = keydict[i]

			k1 = AnonCrypto.pub_key_from_str(s1)
			k2 = AnonCrypto.pub_key_from_str(s2)
			k1.check_key()
			k2.check_key()
			self.pub_keys[i] = (k1, k2)

		self.info('Unpickled public keys')

	def unpickle_pub_keys(self, msgs):
		"""
		Method that the leader uses to unpack
		public keys from other nodes.
		"""
		addrs = []
		for data in msgs:
			(rem_id, rem_round, rem_ip, rem_port,
			 rem_key1, rem_key2) = cPickle.loads(data)
			self.debug("Unpickled msg from node %d" % (rem_id))
			
			if rem_round != self.round_id:
				raise RuntimeError, "Mismatched round numbers!\
					(mine: %d, other: %d)" % (
						self.round_id, rem_round)

			self.pub_keys[rem_id] = (
					AnonCrypto.pub_key_from_str(rem_key1),
					AnonCrypto.pub_key_from_str(rem_key2))
			addrs.append((rem_ip, rem_port))
		return addrs

	def phase0_msg(self):
		""" Message all nodes send to the leader. """
		return cPickle.dumps(
				(self.id,
					self.round_id, 
					self.ip,
					self.port,
					self.key_from_file(1),
					self.key_from_file(2)))
	
	def phase0b_msg(self):
		""" Message the leader sends to all other nodes. """
		newdict = {}
		for i in xrange(0, self.n_nodes):
			k1,k2 = self.pub_keys[i]
			newdict[i] = (
				AnonCrypto.pub_key_to_str(k1),
				 AnonCrypto.pub_key_to_str(k2))

		return cPickle.dumps((self.round_id, newdict))

	"""
	PHASE 1

	Message descriptor generation.
	"""

	def run_phase1(self):
		self.seeds = []
		self.gens = []	
		self.my_hashes = []
		for i in xrange(0, self.n_nodes):
			seed = AnonCrypto.random_seed()
			self.seeds.append(seed)
			self.gens.append(AnonRandom(seed))

		self.msg_len = os.path.getsize(self.msg_file)
		(handle, self.cip_file) = tempfile.mkstemp()

		blocksize = 8192

		"""
		The hash h holds a hash of the XOR of all
		pseudo-random strings with the author's message.
		"""
		h = M2Crypto.EVP.MessageDigest('sha1')
		self.debug('Starting to write data file')

		with open(self.msg_file, 'r') as f_msg:
			with open(self.cip_file, 'w') as f_cip:
				""" Loop until we reach EOF """
				while True:
					block = f_msg.read(blocksize)
					n_bytes = len(block)
					if n_bytes == 0: break

					"""
					Get blocksize random bytes for each other node
					and XOR them together with blocksize bytes of
					my message, update the hash and write the XOR'd
					block out to disk.
					"""
					for i in xrange(0, self.n_nodes):
						""" Don't XOR bits for self """
						if i == self.id: continue

						r_bytes = self.gens[i].rand_bytes(n_bytes)
						#self.debug("l1: %d, l2: %d, n: %d" % (len(block), len(r_bytes), n_bytes))
						block = Utilities.xor_bytes(block, r_bytes)
					f_cip.write(block)
					h.update(block)

		self.debug('Finished writing my data file')

		""" Encrypt each of the pseudo-random generator seeds. """ 
		self.enc_seeds = []
		for i in xrange(0, self.n_nodes):
			self.my_hashes.append(self.gens[i].hash_value())
			# Encrypt each seed with recipient's primary pub key
			self.enc_seeds.append(
					AnonCrypto.encrypt_with_rsa(
						self.pub_keys[i][0],
						self.seeds[i]))
		
		""" Insert "cheating" hash for self. """
		self.my_hashes[self.id] = h.final()

		""" Remember the seed encrypted for self. """
		self.my_seed = self.enc_seeds[self.id]

		""" Write all the data to be sent out to disk. """
		(dhandle, self.dfilename) = tempfile.mkstemp()
		with open(self.dfilename, 'w') as f:
			cPickle.dump((
				self.id,
				self.round_id,
				self.msg_len,
				self.enc_seeds,
				self.my_hashes), f)
		return

	"""
	PHASE 2

	Data exchange.
	"""
	def run_phase2(self):
		""" Start up a shuffle node"""
		s = shuffle_node(
			self.id,
			self.key_len,
			self.round_id,
			self.n_nodes,
			(self.ip, self.port),
			self.leader_addr,
			self.prev_addr,
			self.next_addr,
			self.dfilename,
			# Max msg length given the number of bits we need to represent the length
			1 << int(ceil(log(os.path.getsize(self.dfilename),2))))
		s.run_protocol()
		fnames = s.output_filenames()

		self.msg_data = []
		for filename in fnames:
			with open(filename, 'r') as f_in:
				(r_id,
				 r_round_id,
				 r_msg_len,
				 r_enc_seeds,
				 r_hashes) = cPickle.load(f_in)
			if self.round_id != r_round_id:
				raise RuntimeError, 'Mismatched round ids'
			if r_id not in xrange(0, self.n_nodes):
				raise RuntimeError, 'Invalid node id'

			self.debug("Got data from node %d.  Msg len: %d" % (r_id, r_msg_len))
			self.msg_data.append((r_msg_len, r_enc_seeds, r_hashes))

#
# PHASE 3
#

	def run_phase3(self):
		self.advance_phase()
		self.info("Starting data transmission phase")

		self.responses = []
		self.go_flag = False

		handle, self.tar_filename = tempfile.mkstemp()
		tar = tarfile.open(
				name = self.tar_filename,
				mode = 'w', # Create new archive
				dereference = True)

		# For each transmission slot
		for i in xrange(0, self.n_nodes):
			debug("Processing data for msg slot %d" % i)
			slot_data = self.msg_data[i]
			msg_len = slot_data[0]
			enc_seeds = slot_data[1]
			hashes = slot_data[2]

			if enc_seeds[self.id] == self.my_seed:
				# If this is my seed, use the cheating message
				self.go_flag = True
				self.responses.append(self.dfilename)
				tar.add(self.cip_file, "%d" % (self.id))
			else:
				# Decrypt seed assigned to me
				seed = AnonCrypto.decrypt_with_rsa(self.key1, enc_seeds[self.id])
				h_val, fname = self.generate_prng_file(seed, msg_len)

				if h_val != hashes[self.id]:
					self.debug("Got: %s, Ex: %s" % (base64.encodestring(h_val), base64.encodestring(hashes[self.id])))
					for q in xrange(0, len(hashes)):
						self.debug("> %d - %s" % (q, base64.encodestring(hashes[q])))
					raise RuntimeError, 'Mismatched hash values'

				tar.add(fname, "%d" % (self.id))
		tar.close()

		if not self.go_flag:
			raise RuntimeError, 'My ciphertext is missing'

		if self.am_leader():
			(fnames, addrs) = self.recv_files_from_n(self.n_nodes - 1)
			fnames.append(self.tar_filename)
			self.master_filename = self.create_master_tar(fnames)
			self.broadcast_file_to_all_nodes(self.master_filename)
		else:
			self.send_file_to_leader(self.tar_filename)
			(fnames, addrs) = self.recv_files_from_n(1)
			self.master_filename = fnames[0]

	def create_master_tar(self, fnames):
		handle, master_filename = tempfile.mkstemp()
		tar = tarfile.open(
				master_filename,
				mode = 'w', # Create new archive
				dereference = True)

		for i in xrange(0, self.n_nodes):
			tar.add(fnames[i], "-1")

		tar.close()
		return master_filename

	def generate_prng_file(self, seed, msg_len):
		(h, filename) = tempfile.mkstemp()
		
		bytes_left = msg_len
		blocksize = 8192

		r = AnonRandom(seed)
		with open(filename, 'w') as f:
			while bytes_left > 0:
				if bytes_left > blocksize: toread = blocksize
				else: toread = bytes_left

				bytes = r.rand_bytes(toread)
				f.write(bytes)

				bytes_left = bytes_left - toread
			
		return (r.hash_value(), filename)

#
# PHASE 4
#

	def run_phase4(self):
		self.advance_phase()
		self.info('Starting phase 4')

		# We should now have a pointer to a master_filename, which
		# is a tar of tars.  Each tar-set contains the message strings
		# for a specific message slot.
		
		handles_to_close, filenames = self.unpack_master_tar(self.master_filename)
		self.data_filenames = []

		for i in xrange(0, len(filenames)):
			self.debug("Processing message slot %d" % i)
			self.data_filenames.append(
					self.process_msg_tar(filenames[i], self.msg_data[i], i))

		for h in handles_to_close: h.close()

	def process_msg_tar(self, handles, descrip_data, slot_n):
		# Process one message slot
		hashes = []

		self.debug("Number of subfiles: %d" % len(handles))

		for i in xrange(0, self.n_nodes):
			# Open all files and keep a running hash for each
			hashes.append(M2Crypto.EVP.MessageDigest('sha1'))

		oh, outfile = tempfile.mkstemp()

		blocksize = 4096 * 16
		more_to_read = True

		# outfile holds the plaintext message for this slot 
		with open(outfile, 'w') as f:
			while more_to_read:
				block_str = ''

				# Iterate through contents from each user
				for i in xrange(0, self.n_nodes):
					bytes = handles[i].read(blocksize)
					hashes[i].update(bytes)

					if bytes == '': 
						more_to_read = False
						break 	# Got to EOF

					# XOR strings together
					if i == 0: block_str = bytes
					else: block_str = Utilities.xor_bytes(block_str, bytes)

				f.write(block_str)

		for i in xrange(0, self.n_nodes):
			hout = hashes[i].final()
			if hout != descrip_data[2][i]:
				raise RuntimeError, "Node %d sent bad hash for slot %d" (i, slot_n)
			handles[i].close()
			
		return outfile

	def unpack_master_tar(self, archive_filename):
		# An array of tar archives -- one for each message
		filenames = []
		handles_to_close = []
		for i in xrange(0, self.n_nodes): filenames.append({})

		tar = tarfile.open(archive_filename, 'r:*')

		# Open the master tar file
		for i in xrange(0, self.n_nodes):
			# Create a new tempfile for each inner tar file.
			# Inner tar holds message data for participant i
			(zero, inner_tar_handle) = self.copy_next_from_tar(tar)

			# Open the inner tar file and iterate through its contents
			innertar = tarfile.open(fileobj=inner_tar_handle, mode='r:*')
			for j in xrange(0, self.n_nodes):
				# filenames[j] holds filenames for message slot j
				node_id, fhandle = self.copy_next_from_tar(innertar)
				filenames[j][node_id] = fhandle
			handles_to_close.append(innertar)
			handles_to_close.append(inner_tar_handle)
		handles_to_close.append(tar)

		return (handles_to_close, filenames)

	def copy_next_from_tar(self, tar):
		finfo = tar.next()
		if finfo == None: raise RuntimeError, 'Missing files in tar'

		# Copy inner contents to a tempfile and save the file
		h = tar.extractfile(finfo)
		'''
		handle, file_name = tempfile.mkstemp()
		with open(file_name, 'w') as f:
			shutil.copyfileobj(h, f, 4096)
		'''
		# Get name of authoring node from filename within tar
		node_id = int(finfo.name)
		return (node_id, h)

#
# Network Utility Functions
#

	def recv_cipher_set(self):
		# data_in arrives as a singleton list of a pickled
		# list of ciphers.  we need to unpickle the first
		# element and use that as our array of ciphertexts
		(data, addrs) = self.recv_from_n(1)
		return cPickle.loads(data[0])

	def broadcast_to_all_nodes(self, msg):
		self.broadcast_using(AnonNet.send_to_addr, msg)

	def broadcast_file_to_all_nodes(self, fname):
		self.broadcast_using(AnonNet.send_file_to_addr, fname)

	def broadcast_using(self, func, arg):
		if not self.am_leader():
			raise RuntimeError, 'Only leader can broadcast'

		# Only leader can do this
		for i in xrange(0, self.n_nodes-1):
			ip, port = self.addrs[i]
			func(ip, port, arg)	

	def send_to_leader(self, msg):
		ip,port = self.leader_addr
		AnonNet.send_to_addr(ip, port, msg)

	def recv_from_n(self, n_backlog):
		return AnonNet.recv_from_n(self.ip, self.port, n_backlog)

	def recv_files_from_n(self, n_backlog):
		return AnonNet.recv_files_from_n(self.ip, self.port, n_backlog)

	def send_file_to_leader(self, filename):
		ip,port = self.leader_addr
		return AnonNet.send_file_to_addr(ip, port, filename)
		

#
# Utility Functions 
#


	def key_from_file(self, key_number):
		return Utilities.read_file_to_str(self.key_filename(key_number))

	def have_all_keys(self):
		return len(self.pub_keys) == self.n_nodes

	def generate_keys(self):	
		info("Generating keypair, please wait...")
		self.key1 = AnonCrypto.random_key(self.key_len)
		self.key2 = AnonCrypto.random_key(self.key_len)
		self.save_pub_key(self.key1, 1)
		self.save_pub_key(self.key2, 2)

		self.pub_keys[self.id] = (
				M2Crypto.RSA.load_pub_key(self.key_filename(1)),
				M2Crypto.RSA.load_pub_key(self.key_filename(2))) 
	
	def save_pub_key(self, rsa_key, key_number):
		rsa_key.save_pub_key(self.key_filename(key_number))

	def key_filename(self, key_number):
		return self.node_key_filename(self.id, key_number)

	def node_key_filename(self, node_id, key_number):
		return "/tmp/anon_node_%d_%d.pem" % (node_id, key_number)

	def debug(self, msg):
		debug(self.debug_str(msg))

	def critical(self, msg):
		critical(self.debug_str(msg))

	def info(self, msg):
		info(" " + self.debug_str(msg))

	def debug_str(self, msg):
		return "(NODE %d, PHZ %d - %s:%d) %s" % (self.id, self.phase, self.ip, self.port, msg)


