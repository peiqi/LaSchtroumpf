# CopyRight 2016 PQSHI

import os

from keystoneauth1 import loading
from keystoneauth1 import session
from novaclient import client

VERSION = `2.1`

def nova(args):

    user = os.environ.get('OS_USERNAME', 'admin')
    passwd = os.environ.get('OS_PASSWORD', 'nomoresecrete')
    project_id = os.environ.get('OS_PROJECT_ID', 'empty project id!')
    url = os.environ.get('OS_AUTH_URL', 'http://127.0.0.1:5000/v2.0')
    
    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(auth_url=url,
                                    username=user,
                                    password=passwd,
				    project_id=project_id)
    sess = session.Session(auth=auth)
    nova = client.Client(VERSION, session = sess)

    if args == all:
        print "currently not supported"
        return
    else:
        server_list = nova.servers.list()
        print "the server_list at beginning is %s" % server_list
        for ser in server_list:
            nova.servers.delete(ser)
        server_list_end = nova.servers.list()
        print "the server_list at end is %s" % server_list_end
        

if __name__ == '__main__':
    nova('x')
