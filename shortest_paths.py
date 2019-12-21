#!/usr/bin/env python3

"""Shortest Path Switching template
CSCI1680

This example creates a simple controller application that watches for
topology events.  You can use this framework to collect information
about the network topology and install rules to implement shortest
path switching.

"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_0

from ryu.topology import event, switches
import ryu.topology.api as topo

from ryu.lib.packet import packet, ether_types
from ryu.lib.packet import ethernet, arp, icmp

from ofctl_utils import OfCtl, OfCtl_v1_0, VLANID_NONE

from topo_manager_example import TopoManager
from collections import defaultdict

from queue import PriorityQueue

INF = 0x3f3f3f3f
para_edges = []


class ShortestPathSwitching(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ShortestPathSwitching, self).__init__(*args, **kwargs)
        self.topology_api_app = self
        self.tm = TopoManager()
        self.switch_host_mac = {}  # 一个switch连的所有host [switch_id] = [host.mac]
        self.mac_host_port = {}  # [host.mac] = [host.port.port_no]

    @set_ev_cls(event.EventSwitchEnter)
    def handle_switch_add(self, ev):
        """
        Event handler indicating a switch has come online.
        """
        switch = ev.switch
        self.logger.warn("Added Switch switch%d with ports:", switch.dp.id)
        for port in switch.ports:
            self.logger.warn("\t%d:  %s", port.port_no, port.hw_addr)

        # TODO:  Update network topology and flow rules
        self.tm.add_switch(switch)
        self.switch_host_mac[switch.dp.id] = list()  # 初始化
        self.update_all_flow_table()

    @set_ev_cls(event.EventSwitchLeave)
    def handle_switch_delete(self, ev):
        """
        Event handler indicating a switch has been removed
        """
        switch = ev.switch

        self.logger.warn("Removed Switch switch%d with ports:", switch.dp.id)
        for port in switch.ports:
            self.logger.warn("\t%d:  %s", port.port_no, port.hw_addr)

        # TODO:  Update network topology and flow rules
        self.tm.delete_switch(switch)
        self.update_all_flow_table()

    @set_ev_cls(event.EventHostAdd)
    def handle_host_add(self, ev):
        """
        Event handler indiciating a host has joined the network
        This handler is automatically triggered when a host sends an ARP response.
        """
        host = ev.host
        self.logger.warn("Host Added:  %s (IPs:  %s) on switch%s/%s (%s)",
                         host.mac, host.ipv4,
                         host.port.dpid, host.port.port_no, host.port.hw_addr)

        # TODO:  Update network topology and flow rules
        self.tm.add_host(host)
        self.switch_host_mac[host.port.dpid].append(host.mac)
        self.mac_host_port[host.mac] = host.port.port_no

        self.update_all_flow_table()

    @set_ev_cls(event.EventLinkAdd)
    def handle_link_add(self, ev):
        """
        Event handler indicating a link between two switches has been added
        """
        link = ev.link
        src_port = ev.link.src
        dst_port = ev.link.dst
        self.logger.warn("Added Link:  switch%s/%s (%s) -> switch%s/%s (%s)",
                         src_port.dpid, src_port.port_no, src_port.hw_addr,
                         dst_port.dpid, dst_port.port_no, dst_port.hw_addr)

        # TODO:  Update network topology and flow rules
        self.update_all_flow_table()

    @set_ev_cls(event.EventLinkDelete)
    def handle_link_delete(self, ev):
        """
        Event handler indicating when a link between two switches has been deleted
        """
        link = ev.link
        src_port = link.src
        dst_port = link.dst

        self.logger.warn("Deleted Link:  switch%s/%s (%s) -> switch%s/%s (%s)",
                         src_port.dpid, src_port.port_no, src_port.hw_addr,
                         dst_port.dpid, dst_port.port_no, dst_port.hw_addr)

        # TODO:  Update network topology and flow rules
        self.update_all_flow_table()

    @set_ev_cls(event.EventPortModify)
    def handle_port_modify(self, ev):
        """
        Event handler for when any switch port changes state.
        This includes links for hosts as well as links between switches.
        """
        port = ev.port
        self.logger.warn("Port Changed:  switch%s/%s (%s):  %s",
                         port.dpid, port.port_no, port.hw_addr,
                         "UP" if port.is_live() else "DOWN")

        # TODO:  Update network topology and flow rules
        self.update_all_flow_table()

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """
       EventHandler for PacketIn messages
        """
        msg = ev.msg

        # In OpenFlow, switches are called "datapaths".  Each switch gets its own datapath ID.
        # In the controller, we pass around datapath objects with metadata about each switch.
        dp = msg.datapath

        # Use this object to create packets for the given datapath
        ofctl = OfCtl.factory(dp, self.logger)
        in_port = msg.in_port
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_ARP:
            arp_msg = pkt.get_protocols(arp.arp)[0]

            if arp_msg.opcode == arp.ARP_REQUEST:
                self.logger.warning("Received ARP REQUEST on switch%d/%d:  Who has %s?  Tell %s",
                                    dp.id, in_port, arp_msg.dst_ip, arp_msg.src_mac)

                # TODO:  Generate a *REPLY* for this request based on your switch state
                mac_answer = 0
                for ip in self.tm.ip_host_mac:
                    if ip == arp_msg.dst_ip:
                        mac_answer = self.tm.ip_host_mac[ip]
                        break

                # ofctl.send_arp(arp_opcode=arp.ARP_REPLY, vlan_id=VLANID_NONE,
                #                dst_mac=arp_msg.src_mac,
                #                sender_mac=arp_msg.src_mac, sender_ip=arp_msg.src_ip,
                #                target_ip=arp_msg.dst_ip, target_mac=mac_answer,
                #                src_port=ofctl.dp.ofproto.OFPP_CONTROLLER,
                #                output_port=in_port
                #                )

                ofctl.send_arp(arp_opcode=arp.ARP_REPLY, vlan_id=VLANID_NONE,
                               dst_mac=arp_msg.src_mac,
                               sender_mac=mac_answer, sender_ip=arp_msg.dst_ip,
                               target_ip=arp_msg.src_ip, target_mac=arp_msg.src_mac,
                               src_port=ofctl.dp.ofproto.OFPP_CONTROLLER,
                               output_port=in_port
                               )
                # self.update_all_flow_table()

                print("_________Send ARP____________")
                # self.update_all_flow_table()

        # elif eth.ethertype != 35020:

    def get_topology_data(self):
        switch_list = topo.get_switch(self.topology_api_app, None)
        switches = [switch.dp.id for switch in switch_list]
        links_list = topo.get_link(self.topology_api_app, None)
        # links = [(link.src.dpid, link.dst.dpid, {'port': link.src.port_no}) for link in links_list]
        links = [(link.src.dpid, link.dst.dpid) for link in links_list]
        link_port_dict = defaultdict(dict)

        for link in links_list:
            link_port_dict[link.src.dpid][link.dst.dpid] = link.src.port_no
        return links, link_port_dict, switches, switch_list
        # 我如何获得一个switch连接的所有主机呢？

        # self.net.add_nodes_from(switches)
        # self.net.add_edges_from(links)

    def Dijkstra(self, n: int, S: int, para_edges: list) -> dict:
        print("Begin  Dijkstra.... ")
        Graph = [[] for i in range(n + 1)]  # 邻接表
        for edge in para_edges:
            u, v = edge
            Graph[u].append(node(v, 1))
        dis = [INF for i in range(n + 1)]
        dis[S] = 0
        pre = {}
        pq = PriorityQueue()
        pq.put(node(S, 0))
        while not pq.empty():
            top = pq.get()
            for i in Graph[top.id]:
                if dis[i.id] > dis[top.id] + i.w:
                    dis[i.id] = dis[top.id] + i.w
                    if top.id != S:
                        pre[i.id] = pre[top.id]
                    else:
                        pre[i.id] = i.id
                    pq.put(node(i.id, dis[i.id]))
        print("END  Dijkstra.... ")
        return pre

    def update_all_flow_table(self):

        links, link_port_dict, switches, switch_list = self.get_topology_data()
        snum = len(self.switch_host_mac)
        if len(links) > 0 and snum >= len(switches):
            print("________Begin update flow table________")
            for i in switch_list:  # i 是 switch ！ 不是 switch.dp.id
                s_dic = self.Dijkstra(snum, i.dp.id, links)
                ofc = OfCtl_v1_0(i.dp, self.logger)
                # 如何获得一个switch连的所有list
                ofp_parser = i.dp.ofproto_parser
                for k in s_dic:  # k 是除i以外所有的 switch的id
                    if s_dic[k] == i.dp.id:  # 等于本身意味着，一步就可以到达
                        next_port = link_port_dict[s_dic[k]][k]
                        print("{} to {} : {}".format(i.dp.id, k, next_port))
                        # print(i.dp.id+" to "+k+" : "+next_port)
                    else:
                        next_port = link_port_dict[i.dp.id][s_dic[k]]
                        print("{} to {} : {}".format(i.dp.id, k, next_port))
                        # print(i.dp.id+" to "+k+" : "+next_port)
                    for host_mac in self.switch_host_mac[k]:
                        ofc.set_flow(dl_dst=host_mac, cookie=0, priority=0, dl_type=0,
                                     actions=[ofp_parser.OFPActionOutput(next_port)])
                    # i 直接连的主机也要明确端口
                    for host_mac in self.switch_host_mac[i.dp.id]:
                        port = self.mac_host_port[host_mac]
                        ofc.set_flow(dl_dst=host_mac, cookie=0, priority=0, dl_type=0,
                                     actions=[ofp_parser.OFPActionOutput(port)])
            print("_________End update flow table___________")


class node:
    def __init__(self, id, w):
        self.id = id
        self.w = w

    def __lt__(self, other):
        return True if self.w < other.w else False
