import { eventSchema, type SearchEvent } from './schema';
import { demoResults } from './demo';
export function subscribeSearch(query:string,endpoint:string|null,onEvent:(e:SearchEvent)=>void,onError:(message:string)=>void):()=>void {
 if(!endpoint){
 const terms=query.toLowerCase().split(/\s+/).filter(x=>x.length>3);
 const results=demoResults.filter(r=>terms.some(t=>JSON.stringify(r).toLowerCase().includes(t)));
 const timers:ReturnType<typeof setTimeout>[]=[];
 timers.push(setTimeout(()=>onEvent({type:'status',message:'Searching the demonstration dataset…'}),100));
 results.forEach((result,i)=>timers.push(setTimeout(()=>onEvent({type:'result',result}),550+i*500)));
 timers.push(setTimeout(()=>onEvent({type:'complete',orderedIds:results.map(r=>r.id)}),700+results.length*500));
 return ()=>timers.forEach(clearTimeout);
 }
 const url=new URL(endpoint,window.location.origin);url.searchParams.set('q',query);
 const stream=new EventSource(url.toString());
 let timeout:ReturnType<typeof setTimeout>;
 const stop=()=>{clearTimeout(timeout);stream.close();};
 const arm=()=>{clearTimeout(timeout);timeout=setTimeout(()=>{stop();onError('The search timed out. Please try again.');},45000);};arm();
 stream.onmessage=(message)=>{try{const parsed=eventSchema.parse(JSON.parse(message.data));arm();onEvent(parsed);if(parsed.type==='complete'||parsed.type==='error')stop();}catch{stop();onError('The backend returned an invalid result. Please retry.');}};
 stream.onerror=()=>{stop();onError('Connection interrupted. Results received so far remain available.');};
 return stop;
}
