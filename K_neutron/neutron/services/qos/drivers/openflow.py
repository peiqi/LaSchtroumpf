# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2013 OpenStack Foundation
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
#

from neutron.common import constants
from neutron.services.qos.drivers import qos_base
from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class OpenflowQoSVlanDriver(qos_base.QoSDriver):
    # TODO(scollins) - refactor into dynamic calls
    # 99% of the code is identical
    def __init__(self, bridge, local_vlan_map):
        self.bridge = bridge
        self.local_vlan_map = local_vlan_map
        # Quick lookup table for qoses that are
        # already present - help determine if it's a create
        # or update. RPC does not distinguish between updates and creates
        self.qoses = {}

    def _create_flow_statement_for_policy(self, policy):
        action = ""
        if constants.TYPE_QOS_DSCP in policy:
            action += "mod_nw_tos=%s" % (int(policy[constants.TYPE_QOS_DSCP])
                                         << 2)
        elif constants.TYPE_QOS_RATELIMIT in policy:
            rate = policy[constants.TYPE_QOS_RATELIMIT]
            LOG.info(_("The rate is %s."), rate)
        return action

    def create_qos_for_network(self, policy, network_id):
        vlmap = self.local_vlan_map[network_id]
        mod_nw_tos = self._create_flow_statement_for_policy(policy)
        if vlmap.segmentation_id:
            # Provider network - just add another action to existing
            # flow that rewrites the VLAN tag ID
            self.bridge.mod_flow(dl_vlan=vlmap.vlan,
                                 actions="mod_vlan_vid=%s,%s,NORMAL" % (
                                     vlmap.segmentation_id, mod_nw_tos)
                                 )
        else:
            self.bridge.add_flow(dl_vlan=vlmap.vlan, actions=mod_nw_tos)
        self.qoses[network_id] = True

    def delete_qos_for_network(self, network_id):
        vlmap = self.local_vlan_map[network_id]
        if vlmap.segmentation_id:
            # Provider network - remove the mod_nw_tos key from
            # the flow
            self.bridge.mod_flow(
                dl_vlan=vlmap.vlan,
                actions="mod_vlan_vid=%s,NORMAL" % vlmap.segmentation_id)
        else:
            self.bridge.delete_flows(dl_vlan=vlmap.vlan)
        del self.qoses[network_id]

    def network_qos_updated(self, policy, network_id):
        if network_id in self.qoses:
            # Remove old flow, create new one with the updated policy
            self.delete_qos_for_network(network_id)
        self.create_qos_for_network(policy, network_id)

    def create_qos_for_port(self, policy, port_id):
        ofport = self.bridge.get_vif_port_by_id(port_id).ofport
        action = self._create_flow_statement_for_policy(policy)
        self.bridge.add_flow(in_port=ofport, actions=action, priority=65535)
        self.qoses[port_id] = True

    def delete_qos_for_port(self, port_id, **kwargs):
        # TODO(scollins) - Find a way to pass in --strict,
        # so we can match just the one flow
        ofport = self.bridge.get_vif_port_by_id(port_id).ofport
        self.bridge.delete_flows(in_port=ofport)
        del self.qoses[port_id]

    def port_qos_updated(self, policy, port_id, **kwargs):
        if port_id in self.qoses:
            # Remove flow, create new one with the updated policy
            self.delete_qos_for_port(port_id)
        self.create_qos_for_port(policy, port_id)
