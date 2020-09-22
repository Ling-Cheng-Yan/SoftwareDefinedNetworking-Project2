# Copyright (C) 2016 Nippon Telegraph and Telephone Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from operator import attrgetter

#from ryu.app 
import broadcast_storm
from ryu.controller import ofp_event
from ryu.controller import dpset
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.lib import hub


class link_monitor13(broadcast_storm.Broadcast_prevent):

	def __init__(self, *args, **kwargs):
		super(link_monitor13, self).__init__(*args, **kwargs)
		self.datapaths = {}
		self.port_down_dp_id = 0
		self.port_down = 0
		self.link_down_list = []
	
	@set_ev_cls(ofp_event.EventOFPStateChange,[MAIN_DISPATCHER, DEAD_DISPATCHER])
	def _state_change_handler(self, ev):
		datapath = ev.datapath
		if ev.state == MAIN_DISPATCHER:
			if datapath.id not in self.datapaths:
				self.logger.debug('register datapath: %016x', datapath.id)
				self.datapaths[datapath.id] = datapath
		elif ev.state == DEAD_DISPATCHER:
			if datapath.id in self.datapaths:
				self.logger.debug('unregister datapath: %016x', datapath.id)
				del self.datapaths[datapath.id]
	
	@set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
	def _flow_stats_reply_handler(self, ev):
		body = ev.msg.body
		msg = ev.msg
		dp = msg.datapath
		ofproto = dp.ofproto
		parser = dp.ofproto_parser
		
		for stat in sorted([flow for flow in body if flow.priority == 1], key=lambda flow: (flow.match['in_port'],flow.match['eth_dst'])):
			match = parser.OFPMatch(in_port=stat.match['in_port'], eth_dst=stat.match['eth_dst'])
			flow_mod = dp.ofproto_parser.OFPFlowMod(dp,1,0,0, dp.ofproto.OFPFC_DELETE,0,0,1, dp.ofproto.OFP_NO_BUFFER,stat.instructions[0].actions[0].port, dp.ofproto.OFPG_ANY, dp.ofproto.OFPFF_SEND_FLOW_REM, match)
			dp.send_msg(flow_mod)
	
	@set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
	def _port_modify_handler(self, ev):
		msg = ev.msg
		reason = msg.reason
		dp = msg.datapath
		ofpport = msg.desc
		ofproto = dp.ofproto
		parser = dp.ofproto_parser
	
		if ((ofpport.state << 31) & 0xffffffff ) >> 31 == 1:
			if ((ofpport.config << 31) & 0xffffffff ) >> 31 == 1:
				print "dp %d port %d down" % (dp.id, ofpport.port_no) 
				if self.port_down_dp_id == 0:
					self.port_down_dp_id = dp.id
					self.port_down = ofpport.port_no
				elif self.port_down_dp_id != 0:
					self.net.remove_edge(self.port_down_dp_id,dp.id)
					self.net.remove_edge(dp.id,self.port_down_dp_id)
					self.link_down_list.append((self.port_down_dp_id,dp.id,self.port_down))
					self.link_down_list.append((dp.id,self.port_down_dp_id,ofpport.port_no))
					self.port_down_dp_id = 0
					self.logger.debug('send stats request: %016x', dp.id)
				for dp in self.datapaths.values():
					req = parser.OFPFlowStatsRequest(dp)
					dp.send_msg(req)
		elif ((ofpport.state << 29) & 0xffffffff ) >> 31 == 1:
			print "dp %d port %d up" % (dp.id, ofpport.port_no) 
			if self.port_down_dp_id == 0:
				self.port_down_dp_id = dp.id
				self.port_down = ofpport.port_no
			elif self.port_down_dp_id != 0:
				if self.port_down_dp_id == dp.id:
					return
				index = 0
				while index < len(self.link_down_list):
					
					if self.link_down_list[index] == (self.port_down_dp_id,dp.id,self.port_down):
						self.net.add_edge(self.port_down_dp_id,dp.id,{'port':self.link_down_list[index][2]})
						self.link_down_list.remove(self.link_down_list[index])
					elif self.link_down_list[index] == (dp.id,self.port_down_dp_id,ofpport.port_no):
						self.net.add_edge(dp.id,self.port_down_dp_id,{'port':self.link_down_list[index][2]})
						self.link_down_list.remove(self.link_down_list[index])
					
				self.port_down_dp_id = 0
				print self.net.edges()
				
