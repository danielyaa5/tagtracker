(()=>{
const $=id=>document.getElementById(id),params=new URLSearchParams(location.search),item=params.get('item');
let map,lineLayer,layer,observations=[],places={},shown=200,controller,visiblePoints=[],pathCoords=[],singlePointZoom=15,fitFrame;
const fmt=t=>new Date(t).toLocaleString();
function fitAllPoints(){
 if(!map||!visiblePoints.length||$('map').hidden)return;
 cancelAnimationFrame(fitFrame);
 fitFrame=requestAnimationFrame(()=>{
  map.invalidateSize({pan:false});
  map.fitBounds(visiblePoints,{padding:[40,40],maxZoom:visiblePoints.length===1?singlePointZoom:19,animate:false});
 });
}
const fitButton=document.createElement('button');fitButton.type='button';fitButton.textContent='Fit all points';fitButton.onclick=fitAllPoints;fitButton.disabled=true;$('filters').append(fitButton);
const linesLabel=document.createElement('label');linesLabel.className='line-toggle';
const linesCheck=document.createElement('input');linesCheck.type='checkbox';linesCheck.id='lines';linesCheck.disabled=true;
linesCheck.checked=params.get('lines')==='1'||localStorage.getItem('tagtracker_lines')==='1';
linesLabel.append(linesCheck,document.createTextNode('Connect lines'));
$('filters').append(linesLabel);
function renderLines(){
 if(!lineLayer)return;
 lineLayer.clearLayers();
 linesCheck.disabled=pathCoords.length<2;
 if(linesCheck.checked&&pathCoords.length>=2){
  L.polyline(pathCoords,{color:'#155fc1',weight:3,opacity:.75,dashArray:'6, 8',lineJoin:'round'}).bindTooltip(`Timeline path (${pathCoords.length} points)`,{sticky:true}).addTo(lineLayer);
 }
}
linesCheck.onchange=()=>{
 if(linesCheck.checked)localStorage.setItem('tagtracker_lines','1');
 else localStorage.removeItem('tagtracker_lines');
 renderLines();
 const url=new URL(location);
 if(linesCheck.checked)url.searchParams.set('lines','1');
 else url.searchParams.delete('lines');
 history.replaceState(null,'',url);
};
new ResizeObserver(fitAllPoints).observe($('map'));

if(window.L){map=L.map('map').setView([25,0],2);L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);lineLayer=L.layerGroup().addTo(map);layer=L.layerGroup().addTo(map);}
else $('map').textContent='The map could not load. Your recorded history is available below.';
function drawRows(){const body=$('history-rows');body.replaceChildren();for(const r of observations.slice(0,shown)){const tr=document.createElement('tr');const a=document.createElement('td');a.textContent=fmt(r.ts);tr.append(a);const b=document.createElement('td');const point=places[r.location];if(point&&map){const button=document.createElement('button');button.className='place-link';button.textContent=r.location;button.onclick=()=>{map.setView([point.lat,point.lon],11);$('map').scrollIntoView({behavior:'smooth',block:'center'});};b.append(button);}else b.textContent=r.location||'Unavailable';tr.append(b);const c=document.createElement('td');c.textContent=r.staleness||'Unknown';tr.append(c);body.append(tr);}$('more').hidden=shown>=observations.length;}
async function load(){if(controller)controller.abort();controller=new AbortController();const query=new URLSearchParams({item,range:$('range').value});$('custom').hidden=$('range').value!=='custom';
if($('range').value==='custom'){if(!$('start').value||!$('end').value){$('map-status').textContent='Choose a start and end date, then apply.';return;}const from=new Date($('start').value+'T00:00:00'),to=new Date($('end').value+'T00:00:00');to.setDate(to.getDate()+1);if(from>=to){$('map-status').textContent='End date must be on or after start date.';return;}query.set('start',from.toISOString());query.set('end',to.toISOString());}
$('map-status').textContent='Loading history…';try{const response=await fetch('/api/history?'+query,{signal:controller.signal});const data=await response.json();if(!response.ok)throw Error(data.error||'Unable to load history');observations=data.rows.slice().reverse();places=data.places;shown=200;pathCoords=[];for(const r of data.rows){if(!places[r.location])continue;const pos=[places[r.location].lat,places[r.location].lon];if(pathCoords.length){const prev=pathCoords[pathCoords.length-1];if(prev[0]===pos[0]&&prev[1]===pos[1])continue;}pathCoords.push(pos);}renderLines();const groups=new Map();for(const r of data.rows){if(!places[r.location])continue;const g=groups.get(r.location)||{first:r.ts,last:r.ts,count:0};g.last=r.ts;g.count++;groups.set(r.location,g);}$('map').hidden=groups.size===0;if(layer){layer.clearLayers();if(groups.size)map.invalidateSize();const bounds=[];for(const [name,g] of groups){const p=places[name],pos=[p.lat,p.lon];bounds.push(pos);const pop=document.createElement('div');const title=document.createElement('strong');title.textContent=name;pop.append(title);for(const text of [p.precision||'Approximate town center',`${g.count} recorded observations`,`First recorded: ${fmt(g.first)}`,`Last recorded: ${fmt(g.last)}`]){pop.append(document.createElement('br'),document.createTextNode(text));}L.circleMarker(pos,{radius:9,color:'#155fc1',weight:2,fillColor:'#3889e8',fillOpacity:.65}).bindPopup(pop).addTo(layer);}visiblePoints=bounds;fitButton.disabled=!bounds.length;singlePointZoom=groups.size===1&&places[groups.keys().next().value].source==='User configured'?15:10;fitAllPoints();}
const unmapped=observations.filter(r=>!places[r.location]);const labels=[...new Set(unmapped.map(r=>r.location||'Unavailable'))];$('map-status').textContent=data.count?`${data.count} observations · ${groups.size} mapped ${groups.size===1?'place':'places'} · History starts ${fmt(data.first)}`:'No observations in this date range.';$('unmapped').textContent=unmapped.length?(groups.size===0&&labels.length===1&&labels[0]==='Home'?`All ${unmapped.length} observations are labeled Home. Set a saved Home location to show them on the map.`:`${unmapped.length} observations without a map position: ${labels.join('; ')}.`):'';drawRows();const url=new URL(location);url.searchParams.set('range',$('range').value);if($('range').value==='custom'){url.searchParams.set('from',$('start').value);url.searchParams.set('through',$('end').value);}else{url.searchParams.delete('from');url.searchParams.delete('through');}if(linesCheck.checked){url.searchParams.set('lines','1');}else{url.searchParams.delete('lines');}history.replaceState(null,'',url);
}catch(e){if(e.name!=='AbortError'){$('map-status').textContent='Could not load this range. '+e.message;lineLayer?.clearLayers();layer?.clearLayers();visiblePoints=[];pathCoords=[];linesCheck.disabled=true;fitButton.disabled=true;$('map').hidden=true;observations=[];drawRows();$('unmapped').textContent='';}}}
$('range').value=['24h','7d','30d','90d','all','custom'].includes(params.get('range'))?params.get('range'):'24h';$('start').value=params.get('from')||'';$('end').value=params.get('through')||'';$('range').onchange=load;$('filters').onsubmit=e=>{e.preventDefault();load();};$('refresh').onclick=load;$('more').onclick=()=>{shown+=200;drawRows();};load();
})();
