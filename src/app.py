from flask import Flask
from fuzzywuzzy import fuzz
import psycopg2
from psycopg2 import sql
from psycopg2 import extras
from configparser import ConfigParser
from flask import request
import simplejson as json
import ipfsApi
from Crypto.Cipher import AES
# from Crypto.Util import Counter
# from Crypto import Random
import csv
import hashlib
import gzip
import os, random, struct
from flask import Response

app = Flask(__name__)

def encrypt_file(key, in_filename, out_filename=None, chunksize=64*1024):

    if not out_filename:
        out_filename = in_filename + '.enc'

    # iv = ''.join(chr(random.randint(0, 0xFF)) for i in range(16))
    iv = os.urandom(16)
    # print ("iv = %s, size = %d" % (str(iv) ,len(iv)))
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


def put_quotes (s):
    quote = "'"
    return quote + s + quote


def get_all_data_fields (conn,region,country):
    cursor = conn.cursor()
    query = 'SELECT source_id,field_label,search_terms from marketplace.source_of_field '

    if region is not None or country is not None:
        query += "WHERE "
        if region is not None:
            query += "region = " + put_quotes(region)

            if country is not None:
                query += " AND country = " + put_quotes(country)

        else:
            query += "country = " + put_quotes(country)

    cursor.execute (query)
    rows = cursor.fetchall()
    # print (rows)
    return rows


def get_all_hits (conn,hitList):

    selectQuery = \
        "SELECT id,name,description,delivery_method,access_url,sample_access_url," + \
        "table_name,num_of_records,search_terms,parameters," + \
        "country,state_province,price_low,price_high,json_schema,date_created,date_modified " + \
        " FROM marketplace.data_source_detail WHERE id in ({}) "


    query = sql.SQL (selectQuery).format(sql.SQL(', ').join(sql.Placeholder()*len(hitList)))

    print (hitList)

    # print (query.as_string(conn))
    # make return result in dictionary
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute (query, hitList)
    rows = cursor.fetchall()
    #print (rows)
    return rows


def prob (s1, a_list):
    if a_list is not None:
        for s2 in a_list:
            if fuzz.WRatio (s1,s2) > 60:
                return 1
            else:
                return 0
    else:
        return 0

@app.route("/")
def hello():
    return "Hello!"

@app.route('/search')
def search():
    terms = request.args.get('terms')
    if terms is not None:
        terms = terms.lower()

    country = request.args.get('country')
    if country is not None:
        country = country.lower()

    region = request.args.get('region')
    if region is not None:
        region = region.lower()

    result = None
    connection = None

    try:
        params = config()
        connection = psycopg2.connect(**params)
        connection.set_client_encoding('UTF8')
        data_collections = get_all_data_fields(connection,region,country)
        hits = []

        for data in data_collections:
            if fuzz.WRatio(terms, data[1]) > 60 or prob(terms,data[2]) > 0:
                if data[0] not in hits:
                    hits.append(data[0])

        if len(hits) > 0:
            result = get_all_hits(connection,hits)
            # print (result)

    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
        return Response("DB error", status=500, mimetype='text/html')
    finally:
        if connection:
            connection.close()

    return Response(json.dumps(result, indent=4, sort_keys=False, default=str), status=200, mimetype='application/json')


def deliver_sample_data (conn,id,limit,output):

    #get published field names
    select_query = "select field_name from marketplace.source_of_field where source_id = " + put_quotes(id)

    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cursor.execute(select_query)
    rows = cursor.fetchall()
    cols = [ x['field_name'] for x in rows ]

    select_query = "select table_name, enc_sample_key from marketplace.data_source_detail where id = " + put_quotes(id)

    cursor.execute(select_query, id)
    row = cursor.fetchone()

    #set default
    if row['enc_sample_key'] == None:
        row['enc_sample_key'] = 'toomanysecrets'

    # 32 bytes encryption keys
    cypher_key = hashlib.sha256(row['enc_sample_key'].encode('utf-8')).hexdigest()[:32]

    print ("key = %s" % cypher_key)

    select_query = "select {} from cherre_sample_data.%s " % row['table_name']  + "limit %s" % limit
    # print (selectQuery)

    limit_query = sql.SQL(select_query).format(sql.SQL(', ').join(map(sql.Identifier, cols)))
    print (limit_query.as_string(conn))
    cursor.execute(limit_query)
    rows = cursor.fetchall()

    json_str = json.dumps(rows, indent=4, sort_keys=False, default=str)
    result_file_name = "/tmp/%s.%s.gz" % (id, output)
    out_file = gzip.open(result_file_name, "w")

    if output == "json":
        out_file.write (json_str.encode('utf8'))
    else:
        csv_writer = csv.DictWriter(out_file,fieldnames=cols)
        csv_writer.writeheader()
        for row in rows:
            csv_writer.writerow (row)

    out_file.close()
    enc_file_name = result_file_name + '.enc'
    encrypt_file(cypher_key.encode('utf8'), result_file_name, enc_file_name)

    #put the file out to ipfs throug Infura service
    server_config = config(section='ipfs')

    print (str(server_config))
    api = ipfsApi.Client(server_config['endpoint'], server_config['port'])
    res = api.add(enc_file_name)

    print (str(res))
    return res


@app.route('/sample/<ds_id>')
def get_data(ds_id):
    limit=request.args.get('limit')
    output_format=request.args.get('format')

    # set defaul
    if limit is None:
        limit = 500

    #default to json
    if output_format is None:
        output_format = 'json'

    try:
        params = config()
        connection = psycopg2.connect(**params)
        connection.set_client_encoding('UTF8')
        file_info= deliver_sample_data (connection,ds_id,limit,output_format)
        return Response(json.dumps(file_info,indent=4, sort_keys=False, default=str) , status=200, mimetype='text/html')

    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
        return Response("server error", status=500, mimetype='text/html')

    finally:
        if (connection):
            connection.close()


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
