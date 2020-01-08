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
from queue import Queue

INF = 0x3f3f3f3f
para_edges = []


class ShortestPathSwitching(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ShortestPathSwitching, self).__init__(*args, **kwargs)
        self.topology_api_app = self
        self.tm = TopoManager()

        self.switch_host_mac = {}  # 一个switch连的所有host的mac地址  switch_id : [host.mac]
        self.switch_host_ip = {}  # 一个switch连的所有host的ip地址  switch_id:[host.ip]
        self.switch_host_port = {}  # 一个switch上的所有连接host的端口 switch_id:[switch.port_id]
        self.switch_host = {}  # 一个switch上的所有连接host实体 switch_id:[host]
        self.mac_host_port = {}  # 一个host连接的switch端口 host.mac:[host.port.port_no]
        self.shortest_path = {}

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
        self.switch_host_ip[switch.dp.id] = list()  # 初始化
        self.switch_host_port[switch.dp.id] = list()  # 初始化
        self.switch_host[switch.dp.id] = list()  # 初始化

        self.update_all_flow_table()  # 更新流表

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
        self.update_all_flow_table()  # 更新流表

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
        # 更新有关拓扑结构的记录
        self.switch_host_mac[host.port.dpid].append(host.mac)
        self.switch_host_ip[host.port.dpid].append(host.ipv4)
        self.switch_host_port[host.port.dpid].append(host.port.port_no)
        self.switch_host[host.port.dpid].append(host)
        self.mac_host_port[host.mac] = host.port.port_no

        self.update_all_flow_table()  # 更新流表

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
        self.update_all_flow_table()  # 更新流表

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
        self.update_all_flow_table()  # 更新流表

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
        self.update_all_flow_table()  # 更新流表

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
                self.logger.warning("Received ARP REQUEST on switch%d/%d:  Who has %s?  Tell %s DST %s",
                                    dp.id, in_port, arp_msg.dst_ip, arp_msg.src_mac, arp_msg.dst_mac)

                # TODO:  Generate a *REPLY* for this request based on your switch state
                mac_answer = 0
                # search for the mac address
                for ip in self.tm.ip_host_mac:
                    if ip == arp_msg.dst_ip:
                        mac_answer = self.tm.ip_host_mac[ip]
                        break
                if mac_answer != 0:
                    # if the mac address exists, controller send the ARP reply
                    ofctl.send_arp(arp_opcode=arp.ARP_REPLY, vlan_id=VLANID_NONE,
                                   dst_mac=arp_msg.src_mac,
                                   sender_mac=mac_answer, sender_ip=arp_msg.dst_ip,
                                   target_ip=arp_msg.src_ip, target_mac=arp_msg.src_mac,
                                   src_port=ofctl.dp.ofproto.OFPP_CONTROLLER,
                                   output_port=in_port
                                   )
                else:
                    # if the mac address does not exist, the ARP request will flood.
                    data = msg.data
                    ofproto = dp.ofproto
                    ofp_parser = dp.ofproto_parser
                    actions = [ofp_parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
                    out_flood = ofp_parser.OFPPacketOut(
                        datapath=dp, buffer_id=msg.buffer_id, in_port=msg.in_port,
                        actions=actions, data=data)
                    dp.send_msg(out_flood)

                print("_________Send ARP____________")

    def get_topology_data(self):
        switch_list = topo.get_switch(self.topology_api_app, None)
        switches = [switch.dp.id for switch in switch_list]
        links_list = topo.get_link(self.topology_api_app, None)
        links = [(link.src.dpid, link.dst.dpid) for link in links_list]
        link_port_dict = defaultdict(dict)

        for link in links_list:
            link_port_dict[link.src.dpid][link.dst.dpid] = link.src.port_no

        self.print_topology(link_port_dict, switches)
        return links, link_port_dict, switches, switch_list

    def print_topology(self, link_port_dict, switches):

        print("__________________________Start Printing Topology____________________________")
        if len(switches) == 1:
            for i in switches:
                print("> Connected  Hosts:")
                if self.switch_host_ip[i] and len(self.switch_host_ip[i]) == 0:
                    print("No connected hosts.")
                else:
                    for h in self.switch_host[i]:
                        print("Edge: switch_{}/port_{}<-> host_ip_{}".format(i, h.port.port_no, h.ipv4))

        for sw in link_port_dict:
            print("* For Switch_{} ---------------------".format(sw))
            print("> Connected Switches :")
            for to_sw in link_port_dict[sw]:
                print("Edge: switch_{}/port_{} <-> switch {}/port_{}".format(sw, link_port_dict[sw][to_sw], to_sw,
                                                                             link_port_dict[to_sw][sw]))
            print("> Connected  Hosts:")
            if self.switch_host_ip[sw] and len(self.switch_host_ip[sw]) == 0:
                print("No connected hosts.")
            else:

                for h in self.switch_host[sw]:
                    print("Edge: switch_{}/port_{}<-> host_ip_{}".format(sw, h.port.port_no, h.ipv4))
        print("__________________________END Printing Topology____________________________")

    def Dijkstra(self, n: int, S: int, para_edges: list) -> (dict, list):
        """
        :param n:
        :param S:
        :param para_edges:
        :return:
        """
        Graph = [[] for i in range(n + 1)]
        for edge in para_edges:
            u, v = edge
            Graph[u].append(node(v, 1))

        dis = [INF for i in range(n + 1)]
        dis[S] = 0

        via = {}
        pre = [0 for i in range(n + 1)]
        paths = [[] for i in range(n + 1)]
        paths[S].append(S)

        pq = PriorityQueue()
        pq.put(node(S, 0))
        while not pq.empty():
            top = pq.get()
            if dis[top.id] < top.w:
                continue
            if top.id != S:
                paths[top.id] = paths[pre[top.id]].copy()
                paths[top.id].append(top.id)
            for i in Graph[top.id]:
                if dis[i.id] > dis[top.id] + i.w:
                    dis[i.id] = dis[top.id] + i.w
                    pre[i.id] = top.id
                    if top.id != S:
                        via[i.id] = via[top.id]
                    else:
                        via[i.id] = i.id
                    pq.put(node(i.id, dis[i.id]))
        return via, paths

    def print_shortest_path(self, switch_list: list):
        print("________________________Start Printing Shortest Path_____________________________")
        if len(switch_list) == 1:
            print("There is only a Single switch in the net work.")
        else:
            for i in switch_list:
                print("* For Switch_{} :".format(i.dp.id))
                for j in range(1, len(switch_list) + 1):
                    print("> Switch_{} to Switch_{} ".format(i.dp.id, j))
                    print(self.shortest_path[i.dp.id][j])
        print("__________________________End Printing Shortest Path_____________________________")

    def update_all_flow_table(self):
        links, link_port_dict, switches, switch_list = self.get_topology_data()
        snum = len(self.switch_host_mac)
        if len(links) > 0 and snum >= len(switches):
            print("________Begin update flow table________")
            for i in switch_list:  # i 是 switch ！ 不是 switch.dp.id
                s_dic, paths = self.Dijkstra(snum, i.dp.id, links)
                self.shortest_path[i.dp.id] = paths
                ofc = OfCtl_v1_0(i.dp, self.logger)
                # 如何获得一个switch连的所有list
                ofp_parser = i.dp.ofproto_parser
                # 最短路径，流表更新
                for k in s_dic:
                    if s_dic[k] == i.dp.id:  # 等于本身意味着，一步就可以到达
                        next_port = link_port_dict[s_dic[k]][k]
                    else:
                        next_port = link_port_dict[i.dp.id][s_dic[k]]
                    ## 用目的地的mac地址进行match
                    for host_mac in self.switch_host_mac[k]:
                        ofc.set_flow(dl_dst=host_mac, cookie=0, priority=0,
                                     actions=[ofp_parser.OFPActionOutput(next_port)])
                    # 交换机直接连的主机也要明确端口
                    for host_mac in self.switch_host_mac[i.dp.id]:
                        port = self.mac_host_port[host_mac]
                        ofc.set_flow(dl_dst=host_mac, cookie=0, priority=0,
                                     actions=[ofp_parser.OFPActionOutput(port)])
        elif len(switches) == 1:
            #当网络中只有一个交换机的时候，特殊处理。
            for i in switch_list:
                ofc = OfCtl_v1_0(i.dp, self.logger)
                ofp_parser = i.dp.ofproto_parser
                for host_mac in self.switch_host_mac[i.dp.id]:
                    port = self.mac_host_port[host_mac]
                    ofc.set_flow(dl_dst=host_mac, cookie=0, priority=0,
                                 actions=[ofp_parser.OFPActionOutput(port)])
        # test flood
        self.update_spanning_tree(snum, links, link_port_dict, switch_list)
        print("_________End update flow table___________")
        self.print_shortest_path(switch_list)

    # Prim 算法用与生成最小生成树
    def Prim(self, n: int, S: int, para_edges: list) -> list:
        """
        :param n: the largest number of nodes (switch_id)
        :param S:  an arbitrary start point (switch_id)
        :param para_edges: the list of the graph edges, in a bidirectional format e.g. [ab,ba]
        :return: a list that contains the edges in the spanning tree
        """
        print("Start Spanning Tree Algorithm...")

        Graph = [[] for i in range(n + 1)]
        for edge in para_edges:
            u, v = edge
            Graph[u].append(node(v, 1))

        dis = [INF for i in range(n + 1)]
        dis[S] = 0

        pre = [-1] * (n + 1)

        pq = PriorityQueue()
        pq.put(node(S, 0))
        while not pq.empty():
            top = pq.get()
            for i in Graph[top.id]:
                if dis[i.id] > i.w:
                    dis[i.id] = i.w
                    pre[i.id] = top.id
                    pq.put(node(i.id, dis[i.id]))

        tree_edges = []
        for i in range(n + 1):
            if pre[i] != -1:
                tree_edges.append((i, pre[i]))
                tree_edges.append((pre[i], i))

        return tree_edges

    def query(self, n: int, S: int, tree_edges: list) -> dict:
        '''Return a dictionary that describes the children of every node.
        'n' is the total number of nodes, S is an arbitrary start point
        in the graph, tree_edges is the list of the tree edges.
        '''
        Graph = [[] for i in range(n + 1)]
        for edge in tree_edges:
            u, v = edge
            Graph[u].append(node(v, 1))

        neighbours = {}
        for i in range(n + 1):
            neighbours[i] = []

        q = Queue()
        q.put(node(S, -1))
        while not q.empty():
            top = q.get()
            for i in Graph[top.id]:
                if i.id != top.w:
                    neighbours[top.id].append(i.id)
                    q.put(node(i.id, top.id))

        return neighbours

    def update_spanning_tree(self, n: int, para_edges: list, link_port_dict, switch_list: list):
        """

        :param n:
        :param para_edges:
        :param link_port_dict:
        :param switch_list:
        :return:
        """
        tree = self.Prim(n, 1, para_edges)
        print("************ Spanning Tree *************")
        print(tree)
        print("*****************************************")
        for i in switch_list:  # 网络中每一个switch都作为root

            print("@ Root: Switch_{} ----------------------------------".format(i.dp.id))

            relationship = self.query(n, i.dp.id, tree)
            for father in switch_list:  # 对于网络中每一个switch
                ofc = OfCtl_v1_0(father.dp, self.logger)
                ofp_parser = father.dp.ofproto_parser
                action_set = list()
                print("> For Switch_{} :".format(father.dp.id))
                # 指定当前交换机要output到其他switch的所有port，添加到action_set中
                for each_child in relationship[father.dp.id]:
                    port = link_port_dict[father.dp.id][each_child]
                    action_set.append(ofp_parser.OFPActionOutput(port))
                    print(" Switch_{}/Port_{} -> Switch_{}".format(father.dp.id, port, each_child))

                # 指定当前交换机要output到其他host的所有port，添加到action_set中
                for host_port in self.switch_host_port[father.dp.id]:
                    action_set.append(ofp_parser.OFPActionOutput(host_port))

                # 更新流表，ARP包通过广播地址和source address的ip地址来match
                for host_ip in self.switch_host_ip[i.dp.id]:
                    for each_ip in host_ip:
                        ofc.set_flow(nw_src=each_ip, dl_dst="ff:ff:ff:ff:ff:ff", cookie=0, priority=0,
                                     dl_type=ether_types.ETH_TYPE_ARP,
                                     actions=action_set)


class node:
    def __init__(self, id, w):
        self.id = id
        self.w = w

    def __lt__(self, other):
        return True if self.w < other.w else False
