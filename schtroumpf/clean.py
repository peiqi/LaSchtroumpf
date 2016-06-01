# CopyRight 2016 PQSHI
import os

from keystoneauth1 import loading
from keystoneauth1 import session
from novaclient import client as nva_client
from neutronclient.v2_0 import client as net_client

VERSION = `2.1`

class Cleaner(object):

    def __init__(self):
        self.USER = os.environ.get('OS_USERNAME', 'admin')
        self.PASS = os.environ.get('OS_PASSWORD', 'nomoresecrete')
        self.PROJECT_ID = os.environ.get('OS_PROJECT_ID', 'empty project id!')
        self.URL = os.environ.get('OS_AUTH_URL', 'http://127.0.0.1:5000/v2.0')

    def nova_cl(self, *args):
        loader = loading.get_plugin_loader('password')
        auth = loader.load_from_options(auth_url=self.URL,
                                        username=self.USER,
                                        password=self.PASS,
                                        project_id=self.PROJECT_ID)
        sess = session.Session(auth=auth)
        nova = nva_client.Client(VERSION, session = sess)

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

    def neutron_cl(self, *args):
        neutron = net_client.Client(username=self.USER,
                                    password=self.PASS,
                                    tenant_id=self.PROJECT_ID,
                                    auth_url=self.URL)

        nets = neutron.list_networks()
        for n in nets["networks"]:
            if n["id"] not in args:
                neutron.delete_network(n["id"])

if __name__ == '__main__':
    cleaner = Cleaner()
    #cleaner.nova_cl(['public'])
    cleaner.neutron_cl(['public'])
