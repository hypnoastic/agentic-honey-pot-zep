/* eslint-disable react/prop-types */
import { useState, useEffect, useRef } from 'react';
import { X, ShieldAlert, Terminal, Activity, RefreshCw } from 'lucide-react';

export default function Dashboard() {
  // Data State
  const [stats, setStats] = useState({ scams_detected: 0, failures: 0, est_cost: 0 });
  const [detections, setDetections] = useState([]);
  const [logs, setLogs] = useState([]);
  const [selectedDetection, setSelectedDetection] = useState(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  
  // UI State
  const [loadingDetections, setLoadingDetections] = useState(true);
  const [hasMoreDetections, setHasMoreDetections] = useState(true);
  
  // Refs
  const logsEndRef = useRef(null);
  const detectionsContainerRef = useRef(null);
  const wsRef = useRef(null);
  const pageRef = useRef(0);

  // 1. Fetch Stats
  const fetchStats = () => {
    fetch('/api/stats')
      .then(res => res.json())
      .then(data => {
        setStats(data);
      })
      .catch(err => console.error("Stats fetch failed", err));
  };

  useEffect(() => {
    fetchStats();
  }, []);

  // 2. Fetch Detections
  const fetchDetections = async (page) => {
    try {
      const res = await fetch(`/api/detections?limit=20&offset=${page * 20}`);
      const data = await res.json();
      if (data.length < 20) setHasMoreDetections(false);
      
      setDetections(prev => page === 0 ? data : [...prev, ...data]);
      setLoadingDetections(false);
    } catch (err) {
      console.error("Detections fetch failed", err);
    }
  };

  useEffect(() => {
    fetchDetections(0);
  }, []);

  // Refresh Handler
  const handleRefresh = async () => {
    setIsRefreshing(true);
    // Reset pagination logic
    pageRef.current = 0;
    setHasMoreDetections(true);
    setLoadingDetections(true);
    
    // Parallel fetch
    await Promise.all([
        fetchStats(),
        fetchDetections(0)
    ]);
    
    // Clear logs if connection lost? No, just keep them.
    setIsRefreshing(false);
  };

  // Infinite Scroll Handler
  const handleScroll = () => {
    if (detectionsContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = detectionsContainerRef.current;
      if (scrollTop + clientHeight >= scrollHeight - 50 && hasMoreDetections && !loadingDetections) {
          pageRef.current += 1;
          fetchDetections(pageRef.current);
      }
    }
  };

  // 3. WebSocket Logs
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws/logs`;
    
    const connect = () => {
        const ws = new WebSocket(wsUrl);
        ws.onopen = () => {
            setLogs(prev => [...prev.slice(-99), { timestamp: new Date().toLocaleTimeString(), message: "Connected to live stream.", type: "success" }]);
        };
        ws.onmessage = (event) => {
            try {
                const log = JSON.parse(event.data);
                setLogs(prev => [...prev.slice(-99), log]);
            } catch (e) {
                console.error("Log parse error", e);
            }
        };
        ws.onclose = () => {
            setTimeout(connect, 3000);
        };
        wsRef.current = ws;
    };
    
    connect();

    return () => {
        if (wsRef.current) wsRef.current.close();
    };
  }, []);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // Load Details
  const handleDetectionClick = async (id) => {
    try {
        const res = await fetch(`/api/detections/${id}`);
        const data = await res.json();
        setSelectedDetection(data);
    } catch (err) {
        console.error("Detail fetch failed", err);
    }
  };


  return (
    <div className="flex flex-col h-screen w-screen bg-black text-white overflow-hidden p-6 font-sans selection:bg-white selection:text-black">
      {/* Dashboard Title */}
      <header className="mb-6 shrink-0 border-b border-zinc-800 pb-4 flex justify-between items-center bg-transparent">
         <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-3">
            DASHBOARD
            <span className="text-xs font-mono text-zinc-500 ml-auto bg-zinc-900 px-2 py-1 rounded border border-zinc-800">AGENTIC HONEY-POT v1.1.0</span>
         </h1>
         
         {/* Refresh Button */}
         <button 
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="p-2 rounded-full hover:bg-zinc-800 transition-all border border-transparent hover:border-zinc-700 group focus:outline-none"
            title="Refresh Data"
         >
            <RefreshCw className={`w-5 h-5 text-zinc-400 group-hover:text-white transition-colors ${isRefreshing ? 'animate-spin text-green-500' : ''}`} />
         </button>
      </header>

      {/* SECTION 1: Top Stats (30%) */}
      <div className="h-[30%] flex space-x-6 mb-6">
        <StatsCard title="Scams Detected" value={stats.scams_detected} sub="Lifetime Total" />
        <StatsCard title="Failures" value={stats.failures} sub="Engagement Stopped" />
        <StatsCard title="Estimated Cost Spent" value={`₹${(stats.est_cost * 84).toFixed(2)}`} sub="Operational Expenditures" color="text-red-400" />
      </div>

      {/* SECTION 2: Bottom Area (70%) */}
      <div className="h-[70%] flex space-x-6">
        
        {/* Left: Past Detections */}
        <div className="w-1/2 bg-zinc-900 border border-zinc-800 rounded-2xl flex flex-col overflow-hidden relative transition-all duration-300">
          <div className="p-4 border-b border-zinc-800 flex justify-between items-center bg-zinc-900/50 backdrop-blur-sm sticky top-0 z-10 shrink-0">
            <h2 className="text-xl font-bold tracking-tight text-white flex items-center gap-2 font-mono">
              <ShieldAlert className="w-5 h-5 text-green-500 animate-pulse" />
              {selectedDetection ? "Detection Details" : "Past Detections"}
            </h2>
            {selectedDetection && (
                <button onClick={() => setSelectedDetection(null)} className="p-1 hover:bg-zinc-800 rounded-full transition-colors">
                    <X className="w-6 h-6 text-zinc-400 hover:text-white" />
                </button>
            )}
          </div>
          
          <div 
            className="flex-1 overflow-y-auto p-4 space-y-3 scrollbar-thin scrollbar-thumb-zinc-700 scrollbar-track-transparent"
            ref={detectionsContainerRef}
            onScroll={handleScroll}
          >
             {selectedDetection ? (
                 <DetectionDetailView data={selectedDetection} />
             ) : (
                 <>
                    {detections.map(d => (
                        <DetectionBanner key={d.id} data={d} onClick={() => handleDetectionClick(d.id)} />
                    ))}
                    {loadingDetections && <div className="text-center text-zinc-500 py-4">Loading...</div>}
                 </>
             )}
          </div>
        </div>

        {/* Right: Live Logs */}
        <div className="w-1/2 bg-black border border-zinc-800 rounded-2xl flex flex-col overflow-hidden">
             <div className="p-4 border-b border-zinc-800 bg-zinc-900/30 shrink-0">
                <h2 className="text-xl font-bold tracking-tight text-white font-mono flex items-center gap-2">
                    <Terminal className="w-5 h-5 text-red-500 animate-pulse" />
                    Live Logs
                </h2>
             </div>
             <div className="flex-1 overflow-y-auto p-4 font-mono text-sm space-y-1 scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent bg-black/50">
                {logs.length === 0 && <div className="text-zinc-600 italic">Waiting for logs...</div>}
                {logs.map((log, i) => (
                    <div key={i} className="break-words">
                        <span className="text-zinc-600 mr-2 shrink-0">[{log.timestamp}]</span>
                        <span className={getLogStyle(log.type)}>
                            {log.message}
                        </span>
                    </div>
                ))}
                <div ref={logsEndRef} />
             </div>
        </div>
      </div>
    </div>
  );
}

const getLogStyle = (type) => {
  switch (type) {
    case 'critical': return 'text-red-600 font-bold';
    case 'error':    return 'text-red-500';
    case 'warning':  return 'text-yellow-500';
    case 'success':  return 'text-green-500';
    case 'planner':  return 'text-purple-400';
    case 'thought':  return 'text-blue-400 italic';
    case 'persona':  return 'text-cyan-400';
    case 'system':   return 'text-zinc-500 font-bold';
    default:         return 'text-zinc-300';
  }
};

function StatsCard({ title, value, sub, color = "text-white" }) {
    return (
        <div className="flex-1 bg-zinc-900 border border-zinc-800 rounded-2xl p-6 flex flex-col justify-center items-center hover:bg-zinc-800/50 transition-colors text-center">
            <h3 className="text-zinc-500 font-medium text-lg uppercase tracking-wider">{title}</h3>
            <p className={`text-6xl font-bold mt-2 ${color} tracking-tighter`}>{value}</p>
            {sub && <p className="text-zinc-600 text-sm mt-2">{sub}</p>}
        </div>
    );
}

function DetectionBanner({ data, onClick }) {
    return (
        <div onClick={onClick} className="p-4 border border-zinc-800 rounded-xl hover:border-zinc-500 hover:bg-zinc-800/30 transition-all cursor-pointer group bg-zinc-900/50 font-mono text-sm">
            <div className="flex justify-between items-center mb-1">
                <span className="text-zinc-200 font-bold text-lg group-hover:text-white transition-colors capitalize">{data.scam_type?.replace('_', ' ') || "Unknown Scam"}</span>
                <span className="text-zinc-500 text-xs font-mono">{new Date(data.timestamp).toLocaleTimeString()}</span>
            </div>
            <div className="flex justify-between items-end">
                <p className="text-sm text-zinc-400 line-clamp-1 flex-1 mr-4">{data.summary}</p>
                {data.confidence && (
                    <span className={`text-xs px-2 py-1 rounded-full ${data.confidence > 0.8 ? 'bg-red-500/20 text-red-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
                        {(data.confidence * 100).toFixed(0)}% Conf
                    </span>
                )}
            </div>
        </div>
    );
}

function DetectionDetailView({ data }) {
    return (
        <div className="space-y-6 animate-in fade-in zoom-in-95 duration-200 font-mono text-sm">
            <div className="bg-zinc-800/50 p-4 rounded-xl border border-zinc-700">
                <h3 className="text-2xl font-bold text-white mb-2 uppercase tracking-tight">{data.scam_type}</h3>
                <p className="text-zinc-300 leading-relaxed">{data.summary}</p>
                <div className="mt-4 flex gap-4 text-sm text-zinc-500 font-mono">
                    <span>ID: {data.id?.slice(0, 8)}</span>
                    <span>{new Date(data.timestamp).toLocaleString()}</span>
                </div>
            </div>

            {data.extracted_entities && Object.keys(data.extracted_entities).length > 0 && (
                <div className="bg-red-900/10 border border-red-900/30 p-4 rounded-xl">
                    <h4 className="text-red-400 font-bold mb-3 flex items-center gap-2">
                        <Activity className="w-4 h-4" /> Extracted Intelligence
                    </h4>
                    <div className="grid grid-cols-1 gap-2">
                        {Object.entries(data.extracted_entities).map(([key, vals]) => (
                            vals && vals.length > 0 && (
                                <div key={key} className="flex flex-col">
                                    <span className="text-xs uppercase text-zinc-500 font-bold">{key.replace('_', ' ')}</span>
                                    <div className="flex flex-wrap gap-2 mt-1">
                                        {vals.map((v, i) => (
                                            <span key={i} className="bg-red-500/10 text-red-300 px-2 py-1 rounded text-sm font-mono border border-red-500/20 select-all">
                                                {typeof v === 'object' ? (v.value || JSON.stringify(v)) : v}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            )
                        ))}
                    </div>
                </div>
            )}

            <div className="space-y-4">
                <h4 className="text-zinc-400 font-bold uppercase text-sm tracking-wider">Conversation Log</h4>
                <div className="space-y-3">
                    {data.messages?.map((msg, i) => (
                        <div key={i} className={`flex ${msg.role === 'assistant' || msg.role === 'honeypot' ? 'justify-end' : 'justify-start'}`}>
                            <div className={`max-w-[80%] p-3 rounded-2xl ${
                                msg.role === 'assistant' || msg.role === 'honeypot'
                                    ? 'bg-blue-600/20 text-blue-100 rounded-tr-sm border border-blue-500/30' 
                                    : 'bg-zinc-800 text-zinc-300 rounded-tl-sm border border-zinc-700'
                            }`}>
                                <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                                <p className="text-[10px] opacity-50 mt-1 text-right">{new Date(msg.timestamp).toLocaleTimeString()}</p>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
