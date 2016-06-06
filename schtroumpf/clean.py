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

        #print "the server_list at end is %s" % server_list_end

    def neutron_cl(self, *args):
        nets = self.neutron.list_networks()
        subnets = self.neutron.list_subnets()
        print subnets
        router_list = self.neutron.list_routers()["routers"]
        self.ports = self.neutron.list_ports()
        for n in nets["networks"]:
	    print n 
	    # this is for exclude networks we want to keep 
            if n["name"] not in args:
		for router in router_list:
		    print "router is %s" % router
		    temp = router["external_gateway_info"]
                    self.neutron.remove_gateway_router(router["id"])
	            #print "gateway router return %s" % n 
		    #if temp["network_id"] is n["id"]:
			 # d'abord, delete the external ports
			 #for n in temp["external_fixed_ips"]:
		         #    self.neutron.remove_interface_router(router["id"],
                         #        {"subnet_id": n["subnet_id"]})
			 # ensuite, delete the interface ports
                    for subnet_id in n["subnets"]:
		         self.neutron.remove_interface_router(router["id"],
                             {"subnet_id": subnet_id})
                    self.neutron.delete_router(router["id"])

                for subnet_id in n["subnets"]:
		    port_id_list = [port["id"] for port in self.ports["ports"]]
		    # dissociate floating ip if possible
		    self.dissociate_fip(port_id_list)
		    self.port_cli(subnet_id)
                    
		    self.neutron.delete_subnet(subnet_id)

                self.neutron.delete_network(n["id"])

    def port_cli(self, args):
        #ports = self.neutron.list_ports()
	for port in self.ports["ports"]:
            for p in port["fixed_ips"]:
                if p["subnet_id"] is args:
                    self.neutron.delete_port(port["id"])
        
    def dissociate_fip(self, *args):
        fip_lists = self.neutron.list_floatingips()["floatingips"]
        for fip in fip_lists:
            if fip["port_id"] in args:
                self.neutron.update_floatingips(fip["id"], 
		                                {'floatingip': {'port_id': None}})

    def router_cl(self, *args):
        router_list = self.neutron.list_routers()["routers"]
        for router in router_list:
            if router["external_gateway_info"]['network_id'] not in args:
                self.neutron.remove_gateway_router(router['id']) 

if __name__ == '__main__':
    cleaner = Cleaner()
    cleaner.nova_cl()
    cleaner.neutron_cl('public')
