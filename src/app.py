from flask import Flask
from configparser import ConfigParser
from flask import request
import simplejson as json
import ipfsApi
from Crypto.Cipher import AES
#import csv
#import hashlib
import gzip
import os, random, struct
from flask import Response
from web3 import Web3, HTTPProvider, IPCProvider, WebsocketProvider
import uuid
import hvac
import time
import logging
import logging.config

app = Flask(__name__)

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M',
                    filename='/app/tmp/settlement.log',
                    filemode='w')
# define a Handler which writes INFO messages or higher to the sys.stderr
console = logging.StreamHandler()
console.setLevel(logging.INFO)
# set a format which is simpler for console use
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
# tell the handler to use this format
console.setFormatter(formatter)
# add the handler to the root logger
logging.getLogger('').addHandler(console)

def encrypt_file(key, in_filename, out_filename=None, chunksize=64*1024):

    if not out_filename:
        out_filename = in_filename + '.enc'

    # iv = ''.join(chr(random.randint(0, 0xFF)) for i in range(16))
    iv = os.urandom(16)
    # logging.info ("iv = %s, size = %d" % (str(iv) ,len(iv)))
    encryptor = AES.new(key, AES.MODE_CBC, iv)
    filesize = os.path.getsize(in_filename)

    with open(in_filename, 'rb') as infile:
        with open(out_filename, 'wb') as outfile:
            outfile.write(struct.pack('<Q', filesize))
            outfile.write(iv)

            while True:
                chunk = infile.read(chunksize)
                if len(chunk) == 0:
                    break
                elif len(chunk) % 16 != 0:
                    chunk += ' '.encode('utf8') * (16 - len(chunk) % 16)

                outfile.write(encryptor.encrypt(chunk))


def decrypt_file(key, in_filename, out_filename=None, chunksize=24*1024):
    """ Decrypts a file using AES (CBC mode) with the
        given key. Parameters are similar to encrypt_file,
        with one difference: out_filename, if not supplied
        will be in_filename without its last extension
        (i.e. if in_filename is 'aaa.zip.enc' then
        out_filename will be 'aaa.zip')
    """

    with open(in_filename, 'rb') as infile:
        origsize = struct.unpack('<Q', infile.read(struct.calcsize('Q')))[0]
        iv = infile.read(16)
        decryptor = AES.new(key, AES.MODE_CBC, iv)

        with open(out_filename, 'wb') as outfile:
            while True:
                chunk = infile.read(chunksize)
                if len(chunk) == 0:
                    break
                outfile.write(decryptor.decrypt(chunk))

            outfile.truncate(origsize)

def config(filename='.database.ini', section='postgresql'):
    # create a parser
    parser = ConfigParser()

    # read config file
    parser.read(filename)

    # get section, default to postgresql
    info = {}
    if parser.has_section(section):
        params = parser.items(section)
        for param in params:
            info [param[0]] = param[1]
    else:
        raise Exception('Section {0} not found in the {1} file'.format(section, filename))

    return info

@app.route("/")
def hello():
    return "Hello!"

@app.route('/tx/send', methods = ['POST'])
def transaction_post ():
    try:
        web3_config = config(section='web3')
        vault_config = config(section='vault')
        vault_conn = hvac.Client(url=vault_config['url'], token=vault_config['token'])
        w3 = Web3(Web3.HTTPProvider(web3_config['chain_ip']))

        with open(web3_config['contract_abi'],'rb') as json_file:
            contract_json = json.load(json_file)

        contract_abi = contract_json['abi']
        token_contract = w3.eth.contract(web3_config['contract_addr'], abi=contract_abi)
        operator_address = token_contract.functions.getOperatorAccount().call()
        logging.info('operator='+operator_address)
        # logging.info('operator='+operator_address)
        body = request.get_json()
        logging.info('pay load= %s' + json.dumps(body))

        if body is None:
            data = dict({'status': 'nodata'})
            Response(json.dumps(data), mimetype='application/json')

        dataset_id = uuid.UUID(body['dataset_id']).bytes #convert UUID to bytes
        file_hash = body['data_hash']
        compression = body['data_compression']
        ipfs_hash = body['data_loc_hash']
        size = body['num_of_records']
        # Ethereum VM does not take floating points, use cents
        price = int(body['trade']*100)
        pricing_unit = body['pricing_unit']
        token_uri = body['access_url']
        buyer_account = body['buyer_wallet_addr']
        seller_account = body['seller_wallet_addr']
        seller_email = body['seller_email']

        # The operator mints a ERC-721 token for the seller
        # Estimate gas need
        gas_price = w3.eth.gasPrice
        estimated_gas = token_contract.functions.mint(
                                            dataset_id,
                                            file_hash,
                                            compression,
                                            ipfs_hash,
                                            size,
                                            price,
                                            pricing_unit,
                                            token_uri,
                                            seller_account).estimateGas({
                                                    'nonce': w3.eth.getTransactionCount(operator_address),
                                                    'from': operator_address
                                                 })

        # logging.info ('estimated gas for minting a token = %d' % estimated_gas)
        logging.info('estimated gas for minting a token = %d' % estimated_gas)
        txn = token_contract.functions.mint(dataset_id,
                                            file_hash,
                                            compression,
                                            ipfs_hash,
                                            size,
                                            price,
                                            pricing_unit,
                                            token_uri,
                                            seller_account).buildTransaction({
                                                    'nonce': w3.eth.getTransactionCount(operator_address),
                                                    'from': operator_address,
                                                    'gas': estimated_gas,
                                                    'gasPrice': gas_price})
        vault_key_query = vault_conn.secrets.kv.v1.read_secret(path='cryptooperator',mount_point='/secret')
        private_key = vault_key_query['data']['pk']
        signed = w3.eth.account.signTransaction(txn, private_key)
        txn_hash = w3.eth.sendRawTransaction(signed.rawTransaction)
        logging.info ("token mint: %s" % str(txn_hash.hex()))
        tx_receipt = w3.eth.gwait_for_transaction_receipt(txn_hash,timeout=360)
        
        mint_event = token_contract.events.MintToken().processReceipt(tx_receipt)
        token_id = mint_event[0]['args']['_tokenId']
        logging.info('token id = %d' % token_id)

        #Supply transaction and gas fees to seller
        current_balance = w3.eth.getBalance(seller_account)
        logging.info('current seller accout %s balance %d' % (seller_account, current_balance))

        if (current_balance ) < Web3.toWei(0.001, 'ether'):
            diff = Web3.toWei(0.001, 'ether') - current_balance
            logging.info ('wei to send: %d' % diff)
            gas = w3.eth.estimateGas({'to':seller_account, 'from':operator_address, 'value': diff})
            signed_txn = w3.eth.account.signTransaction(dict(
                                    nonce=w3.eth.getTransactionCount(operator_address),
                                    to=seller_account,
                                    gas = gas,
                                    gasPrice = gas_price,
                                    value = diff
                                  ),
                                  private_key)

            txn_hash = w3.eth.sendRawTransaction(signed_txn.rawTransaction)
            logging.info ('tranfer tx hash-> %s' % str(txn_hash.hex()))
            logging.info('waiting for transaction to be mined')
            tx_receipt = w3.eth.gwait_for_transaction_receipt(txn_hash,timeout=360)

        # Transfer the data token from seller to buyer
        gas = token_contract.functions.purchaseWithFiat(token_id, 0, buyer_account).estimateGas(
            {'nonce': w3.eth.getTransactionCount(seller_account),
             'from': seller_account})

        logging.info('estimate gas = %d' % gas)
        txn = token_contract.functions.purchaseWithFiat(token_id,0, buyer_account)\
            .buildTransaction({'nonce': w3.eth.getTransactionCount(seller_account),
                               'from': seller_account,
                               'gas': gas,
                               'gasPrice': w3.eth.gasPrice})
        logging.info ('seller account = %s' % seller_account)
        kv_path = str(seller_email.encode('utf-8').hex()) + '-1'
        vault_key_query = vault_conn.secrets.kv.v1.read_secret(path=kv_path, mount_point='/secret')
        private_key = vault_key_query['data']['pk']
        signed = w3.eth.account.signTransaction(txn, private_key)
        txn_hash = w3.eth.sendRawTransaction(signed.rawTransaction)
        logging.info ('waiting token transfer receipt = %s' % txn_hash)
        tx_receipt = w3.eth.gwait_for_transaction_receipt(txn_hash,timeout=360)
        
        tx_hash_str = str(txn_hash.hex())
        logging.info('txn hash = %s' % tx_hash_str)
        data = dict({'status':'ok','token_id': token_id, 'txn_hash':tx_hash_str})
        return Response(json.dumps(data), mimetype='application/json')

    except Exception as e:
        logging.error("Ouch Exception occurred", exc_info=True)
        data = dict({'status':'failed','error':'settlement error check /app/tmp/orderlog'})
        return Response(json.dumps(data), mimetype='application/json')

@app.route('/decrypt/<key>/<file_hash>')
def decrpt_has (key,file_hash):
    server_config = config(section='ipfs')
    api = ipfsApi.Client(server_config['endpoint'], server_config['port'])
    api.get(file_hash)
    outfile_name = 'plaintext.gz'
    decrypt_file(key.encode('utf-8'),file_hash, outfile_name)
    with gzip.open(outfile_name, "r") as file:
        data = file.read()

    return Response (data, mimetype='application/json')

if __name__ == '__main__':
    ssl = config(section='ssl')
    context = (ssl['cert'], ssl['key'])
    app.run(ssl_context=context,threaded=True)
    #app.run(threaded=True)
