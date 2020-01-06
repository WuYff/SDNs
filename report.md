# SDNs 
CS305 final project

11712738 武羿
11712121 胡玉斌
11612003 彭可
# Background 
## SDN


## RYU

## Mininet




# Implementation
## Function 1 Controller handle ARP packet

## Function 2 Update Flow Table
### code structure
![](./images/r1.png)
### Method Details
update_all_flow_table()
get_topology_data()
update_spanning_tree()
Prim()
query()
**Dijsktra()**: Given a source node S, caculate the shortest path form S to all the other nodes in the current network topology graph.
**print_shortest_path()** : Print shortest paths for every switch.

## Bonus

# Test
## For mininet triangle
![](./images/t.png)
1. Test command 'pingall'

![](./images/pingall.png)

2. ping an unexist ip address 10.0.0.100

![](./images/ping_2.png)

Use TCPDUMP to capture arp  packet
No flood ,only 3 ARP request packtes captured.

![](./images/tcpdump_2.png)

3. Print Shortest Path
![](./images/shortest_1_triangle.png)

4. Print topology graph
![](./images/triangle_totology.png)

5. Print Spanning Tree
Notice that for each edge, we print bidirectionally.

![](./images/spanning_tree.png)

![](./images/sp_red.png)

6. Change topology
![](./images/change.png)

![](./images/t1.png)

Shortest Path after change

![](./images/shortest_path_after_change.png)

Spanning tree and topology after change

![](./images/spanning_tree_new.png)

Flow table after change

![](./images/flow_table_after_change.png)

# Contribution
name | Percentage |   Task 
-|-|-
武羿 | 33.3%|  |
胡玉斌 | 33.3% |  |
彭可 | 33.3% | |

