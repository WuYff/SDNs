from queue import PriorityQueue

INF = 0x3f3f3f3f
para_edges = []


class node:
    def __init__(self, id, w):
        self.id = id
        self.w = w

    def __lt__(self, other):
        return True if self.w < other.w else False


def Dijkstra(n: int, S: int, para_edges) -> dict:
    print("ASADSASD")
    Graph = [[] for i in range(n + 1)]
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
    return pre

if __name__ == '__main__':
    m = 10
    for i in range(10):
        u, v = map(int, input().split())
        para_edges.append([u, v])
        para_edges.append([v, u])
    print(Dijkstra(9, 1))