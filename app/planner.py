"""Standalone group planner: published timetables, explicit approximate walking."""
from __future__ import annotations
import hashlib,math
from datetime import date,datetime,time,timedelta
from zoneinfo import ZoneInfo
from .gtfs import load_network,seconds
WALK_SPEED=1.25
BUFFER=180


def distance(a,b):
    pa,pb=math.radians(float(a['lat'])),math.radians(float(b['lat']))
    dp=pb-pa;dl=math.radians(float(b['lon'])-float(a['lon']))
    q=math.sin(dp/2)**2+math.cos(pa)*math.cos(pb)*math.sin(dl/2)**2
    return 6371000*2*math.atan2(math.sqrt(q),math.sqrt(max(0,1-q)))


def stamp(day,sec):return (datetime.combine(day,time(),tzinfo=ZoneInfo('Europe/Paris'))+timedelta(seconds=sec)).isoformat()


def walking_key(a,b):
    return tuple(round(float(x),6) for x in (a['lat'],a['lon'],b['lat'],b['lon']))


def walk(a,b,start,costs=None):
    network=(costs or {}).get(walking_key(a,b))
    dm=network['distance_m'] if network else distance(a,b)
    duration=math.ceil(network['duration_seconds']) if network else math.ceil(dm/WALK_SPEED)
    leg={'mode':'walk','from_name':a.get('name','Starting point'),'to_name':b.get('name','Venue'),'dep':start,'arr':start+duration,'distance_m':dm,'geometry':[[float(a['lat']),float(a['lon'])],[float(b['lat']),float(b['lon'])]],'geometry_kind':'approximate_straight_line','estimated':True,'routing_endpoints':[[float(a['lat']),float(a['lon'])],[float(b['lat']),float(b['lon'])]]}
    if network:leg.update({k:v for k,v in network.items() if k not in {'cached_at','duration_seconds'}})
    return leg


def transit(c,stops):
    a,b=stops[c['from']],stops[c['to']]
    return {'mode':c['mode'],'from_name':a['name'],'to_name':b['name'],'dep':c['dep'],'arr':c['arr'],'distance_m':distance(a,b),'trip_id':c['trip_id'],'route_name':c['route_name'],'headsign':c.get('headsign',''),'connection':c}


def shape_geometry(c,stops,data_dir=None):
    a,b=stops[c['from']],stops[c['to']];shape=c.get('shape') or []
    if shape:
        i=min(range(len(shape)),key=lambda i:(shape[i][0]-a['lat'])**2+(shape[i][1]-a['lon'])**2)
        j=min(range(len(shape)),key=lambda i:(shape[i][0]-b['lat'])**2+(shape[i][1]-b['lon'])**2)
        if j>i:return shape[i:j+1],'gtfs_shape'
    if c.get('mode')=='train':
        from .rail_geometry import rail_shape
        corridor=rail_shape(a,b,data_dir)
        if corridor:return corridor['geometry'],'sncf_rail_corridor'
    return [[a['lat'],a['lon']],[b['lat'],b['lon']]],'schematic'


def materialise(path,stops,day,data_dir=None,geometry_cache=None,detailed=True):
    legs=[]
    if geometry_cache is None:geometry_cache={}
    for raw in path:
        leg=dict(raw)
        if 'connection' in leg:
            c=leg.pop('connection')
            key=(c['trip_id'],c['from'],c['to'],c['dep'],c['arr'])
            if key not in geometry_cache:
                geometry,kind=shape_geometry(c,stops,data_dir) if detailed else ([[stops[c['from']]['lat'],stops[c['from']]['lon']],[stops[c['to']]['lat'],stops[c['to']]['lon']]],'schematic')
                length=sum(distance({'lat':a[0],'lon':a[1]},{'lat':b[0],'lon':b[1]}) for a,b in zip(geometry,geometry[1:]))
                geometry_cache[key]=(geometry,kind,length)
            geometry,leg['geometry_kind'],leg['distance_m']=geometry_cache[key]
            # A merged trip extends this list in place; never mutate the cache.
            leg['geometry']=list(geometry)
        if legs and leg.get('trip_id') and legs[-1].get('trip_id')==leg['trip_id']:
            prev=legs[-1];prev['to_name']=leg['to_name'];prev['arr']=leg['arr'];prev['distance_m']+=leg['distance_m'];prev['geometry']+=leg['geometry'][1:]
            if leg['geometry_kind']=='schematic':prev['geometry_kind']='schematic'
        else:legs.append(leg)
    for leg in legs:
        dep,arr=leg.pop('dep'),leg.pop('arr');leg['duration_minutes']=round((arr-dep)/60,2);leg['departure']=stamp(day,dep);leg['arrival']=stamp(day,arr);leg['distance_m']=round(leg['distance_m'])
    return legs



def indoor_leg(venue,start):
    route=venue.get('_indoor_route')
    if not route:return None
    geometry=[[n['lat'],n['lon']] for n in route['nodes'] if n.get('lat') is not None and n.get('lon') is not None]
    return {'mode':'walk','from_name':route['nodes'][0].get('name','Building entrance'),
        'to_name':route['nodes'][-1].get('name','Meeting room'),
        'dep':start,'arr':start+math.ceil(route['duration_seconds']),
        'distance_m':route.get('distance_m',0),'distance_unknown':'distance_m' not in route,
        'geometry':geometry,'geometry_kind':'verified_indoor_graph','estimated':False,
        'instructions':route['instructions'],'indoor':True}

def journeys(person,venues,stops,connections,transfers,day,data_dir=None,walking_costs=None,geometry_cache=None,detailed=True):
    departure=seconds(person['available_from']);deadline=seconds(person['available_until']);maxwalk=float(person.get('max_walk_minutes',30))*60;modes=person.get('modes',['walk','transit'])
    transit_ok=any(m in modes for m in ['transit','bus','train']);labels={};onboard={}
    def preference(label):
        return (label['boardings'],label['walk'],label['route_distance'])
    def dominates(a,b):
        return (a.get('blocked',False)==b.get('blocked',False) and a['ready']<=b['ready'] and a['arrival']<=b['arrival'] and a['walk']<=b['walk'] and a['boardings']<=b['boardings'] and (a['boardings']<b['boardings'] or a['walk']<b['walk'] or a['route_distance']<=b['route_distance']))
    def retain(frontier,label):
        if any(dominates(x,label) for x in frontier):return False
        frontier[:]=[x for x in frontier if not dominates(label,x)]
        frontier.append(label)
        return True
    def add(sid,label):return retain(labels.setdefault(sid,[]),label)
    if transit_ok:
        for sid,s in stops.items():
            dm=distance(person,s)
            if dm<=maxwalk*WALK_SPEED or walking_key(person,s) in (walking_costs or {}):
                leg=walk(person,s,departure,walking_costs)
                elapsed=leg['arr']-leg['dep']
                if elapsed>maxwalk:continue
                add(sid,{'arrival':leg['arr'],'ready':leg['arr']+int(person.get('boarding_margin_minutes',0)*60),'walk':elapsed,'path':[leg],'alight':sid,'last_trip':None,'stop':sid,'boardings':0,'route_distance':leg['distance_m']})
        forbidden=set();minimum={}
        for tr in transfers:
            a,b=tr['from_stop_id'],tr['to_stop_id']
            if tr.get('transfer_type')=='3':forbidden.add((a,b))
            elif tr.get('min_transfer_time'):
                try:minimum[a,b]=int(tr['min_transfer_time'])
                except ValueError:pass
        grid={};neighbors={};transfer_walks={}
        for sid,s in stops.items():grid.setdefault((int(s['lat']/.01),int(s['lon']/.01)),[]).append(sid)
        def nearby(sid):
            if sid not in neighbors:
                s=stops[sid];gx,gy=int(s['lat']/.01),int(s['lon']/.01)
                neighbors[sid]=[]
                for dx in [-1,0,1]:
                    for dy in [-1,0,1]:
                        for tid in grid.get((gx+dx,gy+dy),[]):
                            if tid==sid:continue
                            dm=distance(s,stops[tid])
                            if dm<=600:neighbors[sid].append((tid,dm))
            return neighbors[sid]
        for c in connections:
            if c['dep']<departure or c['arr']>deadline:continue
            if c['mode'] not in modes and 'transit' not in modes:continue
            candidates=[]
            for previous in onboard.get(c['trip_id'],[]):
                if previous['stop']==c['from'] and previous['arrival']<=c['dep']:candidates.append((previous,True))
            if c.get('pickup',True):candidates.extend((x,False) for x in labels.get(c['from'],[]) if x['ready']<=c['dep'] and not x.get('blocked',False))
            if not candidates:continue
            # Keep both low-walking and low-boarding alternatives. Choosing just
            # one here can destroy either a feasible walk-budget path or the
            # simpler journey before the destination is reached.
            frontier=[];segment=transit(c,stops);best_walk=math.inf
            candidates.sort(key=lambda item:(item[0]['boardings']+(0 if item[1] else 1),item[0]['walk'],item[0]['route_distance']))
            for x,staying in candidates:
                # All candidates on this connection have identical arrival and
                # readiness: in preference order only a smaller walking resource
                # can justify keeping another label. Avoid building dominated paths.
                if x['walk']>=best_walk:continue
                best_walk=x['walk']
                new={'arrival':c['arr'],'ready':c['arr']+max(BUFFER,minimum.get((c['to'],c['to']),0)),'walk':x['walk'],'path':x['path']+[segment],'alight':c['to'],'last_trip':c['trip_id'],'stop':c['to'],'blocked':(c['to'],c['to']) in forbidden,'boardings':x['boardings']+(0 if staying else 1),'route_distance':x['route_distance']+segment['distance_m']}
                frontier.append(new)
            onboard[c['trip_id']]=frontier
            if not c.get('dropoff',True):continue
            for new in frontier:
                # Dominated alighting does not remove same-vehicle continuation.
                if not add(c['to'],new):continue
                for tid,dm in nearby(c['to']):
                    if (c['to'],tid) in forbidden:continue
                    pair=(c['to'],tid)
                    if pair not in transfer_walks:transfer_walks[pair]=walk(stops[c['to']],stops[tid],0,walking_costs)
                    template=transfer_walks[pair];elapsed=template['arr']
                    if new['walk']+elapsed>maxwalk:continue
                    leg={**template,'dep':c['arr'],'arr':c['arr']+elapsed}
                    ready=max(leg['arr']+BUFFER,c['arr']+minimum.get(pair,0))
                    add(tid,{'arrival':leg['arr'],'ready':ready,'walk':new['walk']+elapsed,'path':new['path']+[leg],'alight':c['to'],'last_trip':c['trip_id'],'stop':tid,'boardings':new['boardings'],'route_distance':new['route_distance']+leg['distance_m']})
    result={}
    for v in venues:
        choices=[]
        if 'walk' in modes:
            leg=walk(person,v,departure,walking_costs)
            if leg['arr']-leg['dep']<=maxwalk and leg['arr']<=deadline:choices.append({'arrival':leg['arr'],'walk':leg['arr']-leg['dep'],'path':[leg],'boardings':0,'route_distance':leg['distance_m']})
        if transit_ok:
            for sid,ls in labels.items():
                dm=distance(stops[sid],v)
                for label in ls:
                    if not any(x['mode']!='walk' for x in label['path']):continue
                    if dm/WALK_SPEED+label['walk']>maxwalk and walking_key(stops[sid],v) not in (walking_costs or {}):continue
                    leg=walk(stops[sid],v,label['arrival'],walking_costs)
                    elapsed=leg['arr']-leg['dep']
                    terminal_margin=int(person.get('_terminal_margin_seconds',0))
                    if elapsed+label['walk']<=maxwalk and leg['arr']+terminal_margin<=deadline:choices.append({'arrival':leg['arr']+terminal_margin,'walk':elapsed+label['walk'],'path':label['path']+[leg],'boardings':label['boardings'],'route_distance':label['route_distance']+leg['distance_m']})
        interior=indoor_leg(v,0)
        if interior:
            extra=interior['arr']
            choices=[{**x,'arrival':x['arrival']+extra,'walk':x['walk']+extra,'path':x['path']+[indoor_leg(v,x['arrival'])]} for x in choices if x['arrival']+extra<=deadline and x['walk']+extra<=maxwalk]
        if not choices:continue
        chosen=min(choices,key=lambda x:(x['arrival'],*preference(x)));legs=materialise(chosen['path'],stops,day,data_dir,geometry_cache,detailed)
        result[v['id']]={'user_id':person['user_id'],'name':person.get('name','Participant'),'arrival_seconds':chosen['arrival'],'arrival':stamp(day,chosen['arrival']),'duration_minutes':round((chosen['arrival']-departure)/60,2),'distance_m':sum(x['distance_m'] for x in legs),'walking_minutes':round(chosen['walk']/60,2),'boardings':chosen['boardings'],'transfers':max(0,chosen['boardings']-1),'legs':legs,'_raw_path':chosen['path']}
        if detailed:result[v['id']].pop('_raw_path',None)
    return result



def arrive_by(person,venue,stops,connections,transfers,day,deadline,original,walking_costs=None):
    """Latest departure using the same resource-constrained scan in reverse time.

    Reversing a timetable graph is a planning operation, not permission to ride a
    real service backwards. Every returned transit leg is its original service.
    """
    if '_raw_path' not in original:return original  # External/test planner contract.
    interior=indoor_leg(venue,0);indoor_seconds=interior['arr'] if interior else 0
    deadline-=indoor_seconds
    horizon=172800
    clock=lambda n:f"{int(n)//3600:02}:{int(n)%3600//60:02}:{int(n)%60:02}"
    reverse_person={**person,'lat':venue['lat'],'lon':venue['lon'],
        'available_from':clock(horizon-deadline),
        'available_until':clock(horizon-seconds(person['available_from'])),
        'boarding_margin_minutes':0,'max_walk_minutes':float(person.get('max_walk_minutes',30))-indoor_seconds/60,
        '_terminal_margin_seconds':int(person.get('boarding_margin_minutes',0)*60)}
    target={**person,'id':'origin','name':person.get('name','Starting point')}
    reverse_connections=[{**c,'from':c['to'],'to':c['from'],'dep':horizon-c['arr'],
        'arr':horizon-c['dep'],'pickup':c.get('dropoff',True),'dropoff':c.get('pickup',True),
        '_original':c} for c in reversed(connections) if c['dep']>=seconds(person['available_from']) and c['arr']<=deadline]
    reverse_connections.sort(key=lambda c:(c['dep'],c['arr']))
    reverse_transfers=[{**t,'from_stop_id':t['to_stop_id'],'to_stop_id':t['from_stop_id']} for t in transfers]
    reverse_costs={}
    for key,value in (walking_costs or {}).items():
        reverse_costs[key[2:]+key[:2]]={**value,'geometry':list(reversed(value.get('geometry',[])))}
    r=journeys(reverse_person,[target],stops,reverse_connections,reverse_transfers,day,
        walking_costs=reverse_costs,detailed=False).get('origin')
    if not r:return original
    path=[]
    for leg in reversed(r['_raw_path']):
        if 'connection' in leg:
            path.append(transit(leg['connection']['_original'],stops))
        else:
            item={**leg,'dep':horizon-leg['arr'],'arr':horizon-leg['dep'],
                'from_name':leg['to_name'],'to_name':leg['from_name'],
                'geometry':list(reversed(leg.get('geometry',[]))),
                'routing_endpoints':list(reversed(leg.get('routing_endpoints',[])))}
            path.append(item)
    boarded=any(l['mode']!='walk' for l in path)
    margin=int(person.get('boarding_margin_minutes',0)*60) if boarded else 0
    if margin and path and path[0]['mode']=='walk':
        path[0]={**path[0],'dep':path[0]['dep']-margin,'arr':path[0]['arr']-margin}
    if interior:path.append(indoor_leg(venue,path[-1]['arr']))
    departure=path[0]['dep'];arrival=path[-1]['arr']
    if departure<seconds(person['available_from']) or arrival>deadline+indoor_seconds:return original
    # A continuous walk can be delayed until the group's agreed meeting time.
    duration=arrival-departure
    return {**original,'arrival_seconds':arrival,'arrival':stamp(day,arrival),
        'departure':stamp(day,departure),'duration_minutes':round(duration/60,2),
        'walking_minutes':round(r['walking_minutes']+indoor_seconds/60,2),'boardings':r['boardings'],
        'transfers':r['transfers'],'distance_m':sum(l['distance_m'] for l in path),
        'legs':materialise(path,stops,day,detailed=False),'_raw_path':path,
        'departure_strategy':'latest_feasible_under_current_routing_model',
        'boarding_margin_minutes':person.get('boarding_margin_minutes',0)}

def _plan_candidates(meeting,participants,venues,data_dir,network,walking_costs=None,geometry_cache=None):
    day=date.fromisoformat(meeting['date']);duration=int(meeting.get('duration_minutes',30))*60
    stops,connections,transfers,status=network;proposals=[];rejections=[];od=[]
    ids=meeting.get('venue_ids') or [];venues=[v for v in venues if v.get('active',True) and (not ids or v['id'] in ids)]
    if not participants:return {'proposals':[],'rejections':[{'reason':'No accepted participants with complete inputs.'}],'od_matrix':[],'data_status':status}
    weekday=['mon','tue','wed','thu','fri','sat','sun'][day.weekday()]
    routable=[v for v in venues if v.get('active',True) and v.get('permitted') is True and v.get('opening_exceptions',{}).get(day.isoformat(),v.get('opening_hours',{}).get(weekday)) and (v.get('capacity') is None or int(v['capacity'])>=len(participants))]
    routes={p['user_id']:journeys(p,routable,stops,connections,transfers,day,data_dir,walking_costs,geometry_cache,False) for p in participants}
    for v in venues:
        reasons=[];itineraries=[]
        if v.get('permitted') is not True:reasons.append('Venue access permission has not been confirmed for this group.')
        if v.get('capacity') is not None and int(v['capacity'])<len(participants):reasons.append('Group exceeds venue capacity.')
        if v.get('min_group_size') and len(participants)<int(v['min_group_size']):reasons.append('Group is smaller than the venue minimum.')
        if v.get('max_booking_minutes') and duration>int(v['max_booking_minutes'])*60:reasons.append('Meeting exceeds maximum booking duration.')
        for p in participants:
            it=routes[p['user_id']].get(v['id'])
            od.append({'user_id':p['user_id'],'venue_id':v['id'],'reachable':bool(it),'arrival':it['arrival'] if it else None,'duration_minutes':it['duration_minutes'] if it else None,'distance_m':it['distance_m'] if it else None,'legs':it['legs'] if it else []})
            if it:itineraries.append(it)
            else:reasons.append(f"{p.get('name','Participant')}: no usable journey within allowed modes, walking limit and availability.")
        hours=v.get('opening_hours',{}).get(['mon','tue','wed','thu','fri','sat','sun'][day.weekday()],[])
        if day.isoformat() in v.get('opening_exceptions',{}):hours=v['opening_exceptions'][day.isoformat()]
        if not hours:
            known_closed=day.isoformat() in v.get('opening_exceptions',{}) or ['mon','tue','wed','thu','fri','sat','sun'][day.weekday()] in v.get('opening_hours',{})
            reasons.append('Closed on the selected date.' if known_closed else 'Opening hours are not verified for this date.')
        start=latest=None
        if hours and len(itineraries)==len(participants):
            earliest=max(x['arrival_seconds'] for x in itineraries);upper=min(seconds(p.get('attendance_until') or p['available_until']) for p in participants)-duration
            for a,b in hours:
                candidate=max(seconds(a),earliest,max(seconds(p.get('attendance_from') or p['available_from']) for p in participants));limit=min(seconds(b)-duration,upper)
                if candidate<=limit and (start is None or candidate<start):start,latest=candidate,limit
            if start is None:reasons.append('The complete meeting cannot fit after everyone arrives.')
        if meeting.get('return_required') or any(p.get('return_required') for p in participants):reasons.append('Return journeys are not supported by this version.')
        if meeting.get('step_free') or any(p.get('step_free') or p.get('accessibility_required') for p in participants):reasons.append('Step-free access is not certified by this version.')
        if reasons:rejections.append({'venue_id':v['id'],'venue_name':v['name'],'reason':' '.join(dict.fromkeys(reasons))});continue
        itineraries=[arrive_by(p,v,stops,connections,transfers,day,start,it,walking_costs) for p,it in zip(participants,itineraries)]
        for row in od:
            if row['venue_id']==v['id']:
                it=next(x for x in itineraries if x['user_id']==row['user_id'])
                row.update(duration_minutes=it['duration_minutes'],arrival=it['arrival'],departure=it.get('departure'))
        conditional=v.get('availability_status') not in {'confirmed','available'} or v.get('capacity') is None
        pid=hashlib.sha256(f"{meeting.get('id','')}:{v['id']}:{start}".encode()).hexdigest()[:20]
        proposals.append({'id':pid,'venue':v,'start':stamp(day,start),'end':stamp(day,start+duration),'latest_start':stamp(day,latest),'conditional':conditional,'availability_note':'External booking / room availability confirmation required; no reservation has been made.' if conditional else 'Marked available in venue data; no external reservation made.','score':{'total_travel_minutes':round(sum(x['duration_minutes'] for x in itineraries),2),'max_travel_minutes':max(x['duration_minutes'] for x in itineraries)},'itineraries':[{k:v for k,v in x.items() if k!='arrival_seconds'} for x in itineraries]})
    if meeting.get('objective')=='min_total':proposals.sort(key=lambda p:(p['score']['total_travel_minutes'],p['start'],p['score']['max_travel_minutes']))
    else:proposals.sort(key=lambda p:(p['start'],p['score']['total_travel_minutes'],p['venue']['id']))
    for i,p in enumerate(proposals):p['rank']=i+1
    return {'proposals':proposals,'rejections':rejections,'od_matrix':od,'data_status':dict(status)}


def plan_meeting(meeting,participants,venues,data_dir):
    """Learn shortlisted walking costs, then rerun the timetable search.

    A longer access/transfer walk changes which scheduled departure is reachable.
    Replaying the old trip and rejecting a venue is not a feasibility search.
    All venue candidates remain available until final selection, so a rejected
    early candidate cannot hide later feasible alternatives.
    """
    from .walking import FootRouter
    from pathlib import Path
    import json
    from .graph import indoor_route
    network_path=Path(data_dir)/'indoor_networks.json'
    indoor_networks=json.loads(network_path.read_text(encoding='utf-8')) if network_path.exists() else {}
    venues=[dict(v) for v in venues]
    for v in venues:
        if v.get('indoor'):
            spec=v['indoor']
            if spec.get('network_id') not in indoor_networks:
                raise ValueError('No verified indoor graph supplied for '+v['name'])
            v['_indoor_route']=indoor_route(indoor_networks[spec['network_id']],spec['entrance_node'],spec['destination_node'])
    router=FootRouter(data_dir)
    router.allow_network=not meeting.get('fast_mode',False)
    network=load_network(data_dir,date.fromisoformat(meeting['date']))
    costs=router.cached_costs();passes=0;capped=False;geometry_cache={}
    # A bounded refinement loop. Public network requests retain FootRouter's
    # configured cap/rate limit; failed lookups are memoised in that same router.
    max_passes=6 if router.enabled and router.allow_network else 1
    for iteration in range(max_passes):
        passes+=1
        result=_plan_candidates(meeting,participants,venues,data_dir,network,costs,geometry_cache)
        if not router.enabled or not router.allow_network:break
        learned=False
        for proposal in result['proposals'][:1]:
            for itinerary in proposal['itineraries']:
                for leg in itinerary['legs']:
                    if leg['mode']!='walk' or leg.get('indoor') or leg.get('distance_m',0)<3:continue
                    geom=leg.get('routing_endpoints') or leg.get('geometry') or []
                    if len(geom)<2:continue
                    a={'lat':geom[0][0],'lon':geom[0][1]};b={'lat':geom[-1][0],'lon':geom[-1][1]}
                    key=walking_key(a,b)
                    if key in costs:continue
                    route=router.route(geom[0],geom[-1])
                    if route:
                        costs[key]=route;learned=True
        if not learned:break
    else:
        # Last learned edges must still be used by a fresh timetable scan.
        capped=True
        result=_plan_candidates(meeting,participants,venues,data_dir,network,costs,geometry_cache)
        passes+=1
    all_proposals=result['proposals']
    total_winner=min(all_proposals,key=lambda p:(p['score']['total_travel_minutes'],p['start'],p['venue']['id'])) if all_proposals else None
    result['selection_evidence']={'objective':meeting.get('objective','earliest'),'candidate_count':len(all_proposals)+len(result['rejections']),'feasible_count':len(all_proposals),'minimum_total_venue_id':total_winner['venue']['id'] if total_winner else None,'minimum_total_minutes':total_winner['score']['total_travel_minutes'] if total_winner else None,'scope':'Enabled catalogue; timetable journeys with cached or explicitly approximate walking.'}
    selected=all_proposals[:1]
    for proposal in selected:
        proposal['id']=hashlib.sha256((proposal['id']+__import__('secrets').token_hex(8)).encode()).hexdigest()[:24]
        proposal['selection_evidence']=result['selection_evidence']
        for itinerary in proposal['itineraries']:
            raw=itinerary.pop('_raw_path',None)
            if raw is not None:itinerary['legs']=materialise(raw,network[0],date.fromisoformat(meeting['date']),data_dir,{})
            itinerary.update(departure=itinerary['legs'][0]['departure'] if itinerary['legs'] else None,meeting_start=proposal['start'])
    for row in result['od_matrix']:
        row.pop('legs',None)
    for proposal in selected:
        for itinerary in proposal['itineraries']:
            itinerary['walking_geometry_complete']=all(l['mode']!='walk' or l.get('geometry_kind') in {'osm_foot_route','verified_indoor_graph'} or l.get('distance_m',0)<3 for l in itinerary['legs'])
        proposal['walking_geometry_complete']=all(i['walking_geometry_complete'] for i in proposal['itineraries'])
        proposal['walking_refined']=bool(costs)
        for row in result['od_matrix']:
            if row['venue_id']==proposal['venue']['id']:
                it=next((i for i in proposal['itineraries'] if i['user_id']==row['user_id']),None)
                if it:row['walking_refinement_status']='complete' if it['walking_geometry_complete'] else 'partial'
    unresolved=any(not p['walking_geometry_complete'] for p in selected)
    incomplete=bool(unresolved or (not selected and router.enabled and (capped or router.errors)))
    planning_status=('feasible_with_unresolved_walking' if unresolved else 'walking_refined' if selected else 'search_incomplete' if incomplete else 'no_feasible_candidate_under_current_model')
    result.update(proposals=selected,planning_incomplete=incomplete,planning_status=planning_status)
    status=result['data_status'];status['warnings']=list(status.get('warnings',[]))
    status['planning_incomplete']=incomplete;status['planning_status']=planning_status
    status['candidate_search_status']=planning_status
    status['pedestrian_routing']={'enabled':router.enabled,'requests':router.requests,'provider':router.base,'shortlist_only':True,'network_on_calculate':router.allow_network,'replanning_passes':passes,'refinement_iteration_limit_reached':capped,'learned_walking_edges':len(costs),'all_returned_walks_routed':bool(selected) and not unresolved}
    if router.enabled and router.allow_network:
        status['warnings'].append('Walking costs learned from shortlisted routes are fed back into timetable search. Later services and alternative venues are searched; global pedestrian-network optimality is not certified.')
        status['warnings'].extend(dict.fromkeys(router.errors))
    if unresolved:status['warnings'].append('Some walking links remain approximate because network routing was unavailable or its lookup budget was reached; the result is not fully validated.')
    return result


def _refine_walking(result,meeting,participants,data_dir):
    """Refine shortlisted journeys only; never keep a missed timetable connection.

    The broad CSA search still uses cheap walking estimates. Returning a refined
    candidate is not a proof of globally optimal pedestrian-network routing.
    """
    from .walking import FootRouter
    router=FootRouter(data_dir)
    if not router.enabled:return result
    people={p['user_id']:p for p in participants};day=date.fromisoformat(meeting['date'])
    duration=int(meeting.get('duration_minutes',30))*60;valid=[]
    def clock(value):
        dt=datetime.fromisoformat(value)
        return int((dt-datetime.combine(day,time(),tzinfo=ZoneInfo('Europe/Paris'))).total_seconds())
    for proposal in result['proposals']:
        refined=[];failure=None
        for itinerary in proposal['itineraries']:
            p=people[itinerary['user_id']];start=seconds(p['available_from']);cursor=start
            legs=[];walk_seconds=0;last_trip=None;had_vehicle=False
            for original in itinerary['legs']:
                leg=dict(original)
                if leg['mode']=='walk':
                    geom=leg.get('geometry') or []
                    network=router.route(geom[0],geom[-1]) if len(geom)>=2 else None
                    elapsed=clock(leg['arrival'])-clock(leg['departure'])
                    if network:
                        leg.update({k:v for k,v in network.items() if k not in {'cached_at','duration_seconds'}})
                        elapsed=int(network['duration_seconds'])
                    leg['departure']=stamp(day,cursor);cursor+=elapsed;leg['arrival']=stamp(day,cursor)
                    leg['duration_minutes']=round(elapsed/60,2);walk_seconds+=elapsed
                else:
                    departure,arrival=clock(leg['departure']),clock(leg['arrival'])
                    buffer=BUFFER if had_vehicle and last_trip!=leg.get('trip_id') else 0
                    if cursor+buffer>departure:
                        failure=f"{p.get('name','Participant')}: the pedestrian route makes a scheduled connection unreachable; this candidate needs replanning."
                        break
                    cursor=arrival;last_trip=leg.get('trip_id');had_vehicle=True
                legs.append(leg)
            if failure:break
            if walk_seconds>float(p.get('max_walk_minutes',30))*60:
                failure=f"{p.get('name','Participant')}: network walking time exceeds the walking limit; candidate needs replanning.";break
            if cursor>seconds(p['available_until']):
                failure=f"{p.get('name','Participant')}: refined arrival exceeds availability.";break
            item={**itinerary,'legs':legs,'arrival':stamp(day,cursor),'duration_minutes':round((cursor-start)/60,2),'walking_minutes':round(walk_seconds/60,2),'distance_m':round(sum(l['distance_m'] for l in legs))}
            item['walking_geometry_complete']=all(l['mode']!='walk' or l.get('geometry_kind')=='osm_foot_route' or l['distance_m']<3 for l in legs)
            refined.append(item)
        if not failure:
            v=proposal['venue'];earliest=max(clock(it['arrival']) for it in refined)
            upper=min(seconds(p.get('attendance_until') or p['available_until']) for p in participants)-duration
            hours=v.get('opening_exceptions',{}).get(day.isoformat(),v.get('opening_hours',{}).get(['mon','tue','wed','thu','fri','sat','sun'][day.weekday()],[]))
            windows=[(max(earliest,seconds(a)),min(upper,seconds(b)-duration)) for a,b in hours]
            windows=[w for w in windows if w[0]<=w[1]]
            if not windows:failure='Refined pedestrian travel leaves no common window containing the full meeting.'
        if failure:
            result['rejections'].append({'venue_id':proposal['venue']['id'],'venue_name':proposal['venue']['name'],'reason':failure,'requires_replanning':True})
            for row in result['od_matrix']:
                if row['venue_id']==proposal['venue']['id']:row['walking_refinement_status']='requires_replanning'
            continue
        begin,latest=min(windows)
        proposal.update({'itineraries':refined,'start':stamp(day,begin),'end':stamp(day,begin+duration),'latest_start':stamp(day,latest),'walking_refined':True,'walking_geometry_complete':all(i['walking_geometry_complete'] for i in refined)})
        proposal['id']=hashlib.sha256(f"{meeting.get('id','')}:{proposal['venue']['id']}:{begin}:foot".encode()).hexdigest()[:20]
        proposal['score']={'total_travel_minutes':round(sum(i['duration_minutes'] for i in refined),2),'max_travel_minutes':max(i['duration_minutes'] for i in refined)}
        for row in result['od_matrix']:
            if row['venue_id']==proposal['venue']['id']:
                it=next((i for i in refined if i['user_id']==row['user_id']),None)
                if it:
                    row.update({k:it[k] for k in ['arrival','duration_minutes','distance_m','legs']});row['walking_refinement_status']='complete' if it['walking_geometry_complete'] else 'partial'
        valid.append(proposal)
    if meeting.get('objective')=='min_total':valid.sort(key=lambda p:(p['score']['total_travel_minutes'],p['start'],p['score']['max_travel_minutes']))
    else:valid.sort(key=lambda p:(p['start'],p['score']['max_travel_minutes'],p['score']['total_travel_minutes']))
    for i,p in enumerate(valid):p['rank']=i+1
    result['proposals']=valid
    status=result['data_status'];warnings=status.setdefault('warnings',[])
    warnings[:]=[w for w in warnings if 'Walking times and geometry' not in w]
    warnings.append('Candidate search uses approximate walking links; shortlisted itineraries are refined with a pedestrian router. Global network optimality is not certified.')
    if any(not p['walking_geometry_complete'] for p in valid):warnings.append('Some walking links could not be routed and remain explicitly approximate.')
    warnings.extend(dict.fromkeys(router.errors))
    status['pedestrian_routing']={'enabled':True,'requests':router.requests,'provider':router.base,'shortlist_only':True,'all_returned_walks_routed':bool(valid) and all(p['walking_geometry_complete'] for p in valid)}
    return result


# Cache complete query rows, not only raw feed parsing. Keep network references
# with each entry so Python object-id reuse cannot produce a false cache hit.
from collections import OrderedDict
from copy import deepcopy
import json as _json
from threading import RLock
_QUERY_CACHE=OrderedDict()
_QUERY_LOCK=RLock()
_uncached_journeys=journeys


def journeys(person,venues,stops,connections,transfers,day,data_dir=None,walking_costs=None,geometry_cache=None,detailed=True):
    if detailed:
        return _uncached_journeys(person,venues,stops,connections,transfers,day,data_dir,walking_costs,geometry_cache,detailed)
    signature=_json.dumps([person,venues,transfers,day.isoformat(),str(data_dir),
        sorted((str(k),v) for k,v in (walking_costs or {}).items())],sort_keys=True,default=str)
    key=(id(stops),id(connections),signature)
    with _QUERY_LOCK:
        cached=_QUERY_CACHE.get(key)
        if cached is not None:
            _QUERY_CACHE.move_to_end(key)
            return deepcopy(cached[2])
    result=_uncached_journeys(person,venues,stops,connections,transfers,day,data_dir,walking_costs,geometry_cache,detailed)
    with _QUERY_LOCK:
        _QUERY_CACHE[key]=(stops,connections,deepcopy(result))
        while len(_QUERY_CACHE)>48:_QUERY_CACHE.popitem(last=False)
    return result


_ARRIVE_CACHE=OrderedDict()
_uncached_arrive_by=arrive_by

def arrive_by(person,venue,stops,connections,transfers,day,deadline,original,walking_costs=None):
    signature=_json.dumps([person,venue,transfers,day.isoformat(),deadline,
        sorted((str(k),v) for k,v in (walking_costs or {}).items())],sort_keys=True,default=str)
    key=(id(stops),id(connections),signature)
    with _QUERY_LOCK:
        cached=_ARRIVE_CACHE.get(key)
        if cached is not None:
            _ARRIVE_CACHE.move_to_end(key)
            return deepcopy(cached[2])
    result=_uncached_arrive_by(person,venue,stops,connections,transfers,day,deadline,original,walking_costs)
    with _QUERY_LOCK:
        _ARRIVE_CACHE[key]=(stops,connections,deepcopy(result))
        while len(_ARRIVE_CACHE)>96:_ARRIVE_CACHE.popitem(last=False)
    return result
