"""Recompute a hypothetical two-station case using genuine imported timetables."""
import json,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from app.planner import plan_meeting
scenario=json.loads((root/'data/reference_scenario.json').read_text(encoding='utf-8'))
scenario['meeting']['fast_mode']=True
venues=json.loads((root/'data/venues.json').read_text(encoding='utf-8'))
t=time.monotonic();result=plan_meeting(scenario['meeting'],scenario['participants'],venues,root/'data')
assert result['data_status']['transit_available'] and result['proposals']
p=result['proposals'][0];print(p['venue']['name'],p['start'],'conditional:',p['conditional'])
for it in p['itineraries']:
 print(it['name'],it['arrival'])
 for l in it['legs']:print(l['mode'],l.get('route_name',''),l['from_name'],'->',l['to_name'],l['departure'],l['arrival'])
print('Seconds:',round(time.monotonic()-t,2));print('Published schedule only; approximate walking and external booking confirmation required.')
