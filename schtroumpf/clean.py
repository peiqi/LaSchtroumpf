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

        self.neutron = net_client.Client(username=self.USER,
                                    password=self.PASS,
                                    tenant_id=self.PROJECT_ID,
                                    auth_url=self.URL)
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
        nets = neutron.list_networks()
        for n in nets["networks"]:
            if n["name"] not in args:
                print "network is %s" % nets
                #for router_id in n["router_id"]:
                    #print "router id is %s" % router_id
                for subnet_id in n["subnets"]:
                    ports = neutron.list_ports(subnet_id)
                    for port in ports["ports"]:
                        neutron.delete_port(port["id"])
                    neutron.delete_subnet(subnet_id)
                
                neutron.delete_network(n["id"])
 
    def dissociate_fip(self, *args):
        fip_lists = self.neutron.list_floatingips()["floatingips"]
        for fip in fip_lists:
            if fip["port_id"] in args:
                self.neutron.delete_floatingips(fip["port_id"])

    def router_cl(self, *args):
        pass

if __name__ == '__main__':
    cleaner = Cleaner()
    #cleaner.nova_cl(['public'])
    cleaner.dissociate_fip()
