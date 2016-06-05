# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2015 OpenStack Foundation
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from oslo_log import log as logging
from neutron.common import constants
from neutron.services.qos.drivers import qos_base

LOG = logging.getLogger(__name__)


class OVSHybridQoSDriver(qos_base.QoSDriver):

    def __init__(self, bridge):
        self.bridge = bridge

    def delete_qos_for_network(self, network_id):
        # not support network QoS
        pass

    def network_qos_updated(self, policy, network_id):
        # not support network QoS
        pass

    def create_qos_for_port(self, policy, port_id, **kwargs):
        '''Create qos for port.

        :param policy: qos policy
        :param port_id: port id
        '''
        port = self.bridge.get_vif_port_by_id(port_id)
        if port:
            port_name = port.port_name
        else:
            LOG.warn(_("port_id:%s has some question to create QoS"), port_id)
            return

        # add ingress ratelimit
        self.bridge.set_db_attribute("interface", port_name,
                                     "ingress_policing_rate",
                                     int(policy[constants.TYPE_QOS_RATELIMIT]))

        # add egress ratelimit
#         self.bridge.run_vsctl(["--", "set", "port", port_name, "qos=@newqos",
#            "--", "--id=@newqos", "create", "qos", "type=linux-htb",
#            queues:0=@newqueue", "--", "--id=@newqueue", "create", "queue",
# "other-config:max-rate=%u" % (int(policy[constants.TYPE_QOS_RATELIMIT])*1000)
#                               ])

    def delete_qos_for_port(self, port_id, **kwargs):
        '''Delete qos for port.

        :param port_id: port id
        '''
        port = self.bridge.get_vif_port_by_id(port_id)
        if port:
            port_name = port.port_name
        else:
            LOG.warn(_("port_id:%s has some question to delete qos"), port_id)
            return

        # delete ingress ratelimit
        self.bridge.set_db_attribute("interface", port_name,
                                     "ingress_policing_rate", 0)

        # delete egress ratelimit
#         self.bridge.run_vsctl(["clear", "port", port_name, "qos"])

    def port_qos_updated(self, policy, port_id, **kwargs):
        '''Update qos for port.

        :param policy: qos policy
        :param port_id: port id
        '''
        self.delete_qos_for_port(port_id)
        self.create_qos_for_port(policy, port_id)

    def port_qos_sync(self, ports_dict):
        '''Sync qos for port.

        :param ports_dict: dict of qos id and qos policy
        '''
        # delete all ratelimit
        for port_id in ports_dict.keys():
            self.delete_qos_for_port(port_id)

        # destroy all qos and queue
#         self.bridge.run_vsctl(["--", "--all", "destroy", "qos"])
#         self.bridge.run_vsctl(["--", "--all", "destroy", "queue"])

        # add ratelimit
        for port_id in ports_dict.keys():
            if ports_dict[port_id]:
                self.create_qos_for_port(ports_dict[port_id], port_id)
