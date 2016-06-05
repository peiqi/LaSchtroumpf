# Copyright 2014, Hewlett-Packard Development Company, L.P.
# All Rights Reserved.
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
import oslo_messaging

from neutron import manager
from neutron.db import qos_db

LOG = logging.getLogger(__name__)


class QoSServerRpcCallback(object):
    """Plugin-side RPC (implementation) for agent-to-plugin interaction.

    This class implements the server side of an rpc interface.
    """

    # History
    #   1.0 Initial version

    target = oslo_messaging.Target(version='1.0',
                                   namespace=None)

    @property
    def plugin(self):
        if not getattr(self, '_plugin', None):
            self._plugin = manager.NeutronManager.get_plugin()
        return self._plugin

    def get_policy_for_qos(self, context, **kwargs):
        result = {}
        qos_id = kwargs.get('qos_id')
        query = context.session.query(qos_db.QoS)
        results = query.filter_by(id=qos_id)
        for policy in results.one().policies:
            result[policy['key']] = policy['value']
        return result

    # modified by bc-vnetwork, bug: BCVSW-149
    def get_port_and_qos_policy(self, context, **kwargs):
        results = {}
        port_id = kwargs.get('port_id', None)
        filter_args = {}
        if port_id is not None:
            filter_args['port_id'] = port_id

        query = context.session.query(qos_db.PortQoSMapping,
                                      qos_db.QoS,
                                      qos_db.QoSPolicy)
        query_results = query.filter_by(**filter_args) \
            .filter(qos_db.PortQoSMapping.qos_id == qos_db.QoS.id) \
            .filter(qos_db.QoSPolicy.qos_id == qos_db.QoS.id)
        for query_result in query_results:
            result = {}
            for policy in query_result.QoS.policies:
                result[policy['key']] = policy['value']
            floating_ip_port_id = query_result.PortQoSMapping.port_id
            if floating_ip_port_id not in results:
                results[floating_ip_port_id] = result
        return results

    def get_qos_by_network(self, context, **kwargs):
        network_id = kwargs.get('network_id')
        query = context.session.query(qos_db.NetworkQoSMapping)
        try:
            mapping = query.filter_by(network_id=network_id).one()
            return mapping.qos_id
        except Exception:
            return []
