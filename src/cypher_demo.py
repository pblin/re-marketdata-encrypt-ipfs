import os, random, struct
from Crypto.Cipher import AES
import hashlib
import sys
import gzip


def decrypt_file(key, in_filename, out_filename=None, chunksize=24*1024):
    """ Decrypts a file using AES (CBC mode) with the
        given key. Parameters are similar to encrypt_file,
        with one difference: out_filename, if not supplied
        will be in_filename without its last extension
        (i.e. if in_filename is 'aaa.zip.enc' then
        out_filename will be 'aaa.zip')
    """
    if not out_filename:
        out_filename = os.path.splitext(in_filename)[0] + '.gz'

    with open(in_filename, 'rb') as infile:
        origsize = struct.unpack('<Q', infile.read(struct.calcsize('Q')))[0]
        iv = infile.read(16)
        decryptor = AES.new(key, AES.MODE_CBC, iv)

        with open(out_filename + '.gz', 'wb') as outfile:
            while True:
                chunk = infile.read(chunksize)
                if len(chunk) == 0:
                    break
                outfile.write(decryptor.decrypt(chunk))

            outfile.truncate(origsize)


def main(argList):

    # key = '9f86d081884c7d659a2feaa0c55ad015'
    key = hashlib.sha256(argList[0].encode('utf-8')).hexdigest()[:32]

    # encrypt_file(key, "/tmp/f92f25b0-3a1d-11e9-a778-1f41c54b70ff.json")
    # decrypt_file(key, "/Users/bernardlin/Downloads/QmfWobqsHG46msBCqdMRcXbBw2cVNot3KffzrN5zGoZmxD", "/tmp/out.json")
    decrypt_file (key.encode('utf8'), argList[1], argList[2])

if __name__ == "__main__":
    main(sys.argv[1:])