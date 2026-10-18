import Navigator from './navigator';
export default function Page(){return <Navigator endpoint={process.env.SEARCH_STREAM_URL || null}/>;}
