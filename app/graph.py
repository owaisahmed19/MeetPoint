"""Course f1: repeated Dijkstra and recoverable, directed shortest paths."""
from heapq import heappop, heappush
from math import inf, isfinite


def dijkstra(graph, origin):
    nodes=set(graph)
    for edges in graph.values():
        for destination,cost in edges:
            if not isfinite(cost) or cost<0:raise ValueError('Dijkstra requires finite non-negative edge costs')
            nodes.add(destination)
    if origin not in nodes:raise ValueError('Unknown origin')
    distances={node:inf for node in nodes};previous={};distances[origin]=0
    queue=[(0,0,origin)];serial=0
    while queue:
        cost,_,node=heappop(queue)
        if cost!=distances[node]:continue
        for destination,weight in graph.get(node,[]):
            candidate=cost+weight
            if candidate<distances[destination]:
                distances[destination]=candidate;previous[destination]=node
                serial+=1;heappush(queue,(candidate,serial,destination))
    return distances,previous


def path(previous, origin, destination):
    result=[destination]
    while result[-1]!=origin:
        if result[-1] not in previous:return []
        result.append(previous[result[-1]])
    return list(reversed(result))


def closure(matrix):
    n=len(matrix)
    if not n or any(len(row)!=n for row in matrix):raise ValueError('Expected a nonempty square matrix')
    graph={i:[] for i in range(n)}
    for i,row in enumerate(matrix):
        for j,w in enumerate(row):
            if w is None or w==-1:continue
            if not isinstance(w,(int,float)) or not isfinite(w) or w<0:raise ValueError('Invalid edge cost')
            graph[i].append((j,w))
    costs=[];routes=[]
    for origin in range(n):
        d,previous=dijkstra(graph,origin)
        costs.append([None if d[j]==inf else d[j] for j in range(n)])
        routes.append([path(previous,origin,j) for j in range(n)])
    return {'algorithm':'Repeated Dijkstra','costs':costs,'routes':routes,'unreachable':None}


def indoor_route(network,origin,destination):
    """Use only an explicitly supplied, verified indoor graph, with given costs."""
    if not network.get('verified'):raise ValueError('Indoor graph is not verified')
    nodes=network.get('nodes',{});graph={node:[] for node in nodes}
    for edge in network.get('edges',[]):
        a,b=edge['from'],edge['to'];cost=float(edge['seconds'])
        if a not in nodes or b not in nodes:raise ValueError('Indoor edge references an unknown node')
        graph[a].append((b,cost))
        if edge.get('bidirectional',False):graph[b].append((a,cost))
    if destination not in nodes:raise ValueError('Unknown indoor destination')
    d,previous=dijkstra(graph,origin)
    if d[destination]==inf:raise ValueError('Indoor destination is unreachable')
    route=path(previous,origin,destination)
    return {'algorithm':'Dijkstra','duration_seconds':d[destination],
        'nodes':[dict(nodes[node],id=node) for node in route],
        'instructions':' → '.join(nodes[node].get('name',node) for node in route)}
