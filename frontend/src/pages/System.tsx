import { ArrowRight, Database, Gauge, Globe, Network, Play, Radio, Server } from "lucide-react";
import { useState } from "react";
import { Card, ErrorBox, Spinner, Stat } from "../components/common";
import { api, type SystemInfo } from "../lib/api";
import { useAsync } from "../lib/hooks";
import { runBurst, type BurstResult } from "../lib/loadtest";

const MODE: Record<SystemInfo["mode"], { title: string; expect: string; nodes: string[] }> = {
  serverless: {
    title: "Serverless (Vercel)",
    expect: "Vercel's edge network routes each request to a function instance and starts more instances as a burst " +
      "arrives, so a large burst is usually answered by many different instances.",
    nodes: ["Browsers", "Vercel edge (load balancer)", "Auto-scaled API instances", "Neon PostgreSQL"],
  },
  replicas: {
    title: "Replicas behind nginx (docker compose)",
    expect: "nginx spreads requests over the API replicas (least connections), so the burst should split roughly evenly. " +
      "Live updates still reach every browser because replicas share Redis pub/sub.",
    nodes: ["Browsers", "nginx load balancer", "API replicas", "PostgreSQL + Redis"],
  },
  single: {
    title: "Single server",
    expect: "One process answers everything. Run `docker compose up --scale api=3` to see load balancing.",
    nodes: ["Browser", "API", "PostgreSQL"],
  },
};

const TOP = 10;   // busiest instances shown as bars; the rest are summarised

/** Short, stable label for an instance id like "4f1c2a9e0b3d:8" or "169.254.40.141:8". */
function label(i: number) {
  return `#${i + 1}`;
}

export function SystemPage() {
  const info = useAsync<SystemInfo>(() => api.system(), []);
  const [size, setSize] = useState(40);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<BurstResult | null>(null);

  if (info.error && !info.data) return <ErrorBox message={info.error} onRetry={info.reload} />;
  if (!info.data) return <Spinner />;
  const s = info.data;
  const m = MODE[s.mode];
  const max = result ? Math.max(...result.instances.map((x) => x.count), 1) : 1;

  async function run() {
    setBusy(true);
    try {
      setResult(await runBurst(size));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>System</h1>
          <p className="sub">How this deployment spreads load, and a live test you can run right now.</p>
        </div>
        <span className="chip">{m.title}</span>
      </div>

      <Card title="Request path">
        <div className="flow">
          {m.nodes.map((n, i) => (
            <span key={n} className="flow-step">
              <span className={`flow-node ${i === 1 && s.mode !== "single" ? "flow-lb" : ""}`}>
                {i === 0 ? <Globe size={16} /> : i === m.nodes.length - 1 ? <Database size={16} /> : i === 1 && s.mode !== "single" ? <Network size={16} /> : <Server size={16} />}
                {n}
              </span>
              {i < m.nodes.length - 1 && <ArrowRight size={16} className="flow-arrow" />}
            </span>
          ))}
        </div>
      </Card>

      <div className="stats">
        <Stat icon={Network} accent="indigo" label="Load balancer" value={s.mode === "single" ? "None" : s.mode === "serverless" ? "Vercel" : "nginx"}
          hint={s.load_balancer} />
        <Stat icon={Radio} accent="sky" label="Live updates" value={s.live_updates.startsWith("Redis") ? "Redis" : s.live_updates.startsWith("Polling") ? "Polling" : "In-process"} hint={s.live_updates} />
        <Stat icon={Gauge} accent="amber" label="Auction closer" value={s.auction_closer.startsWith("Celery") ? "Celery" : s.auction_closer.startsWith("on") ? "On request" : "Background"}
          hint={s.auction_closer} />
        <Stat icon={Server} accent="violet" label="This page served by" value={<span className="mono stat-mono">{s.instance}</span>} hint="X-Served-By of /api/system" />
      </div>

      <Card title="Load-balancing test" actions={
        <div className="burst-controls">
          <select value={size} onChange={(e) => setSize(Number(e.target.value))} aria-label="Burst size">
            {[20, 40, 80].map((n) => <option key={n} value={n}>{n} requests</option>)}
          </select>
          <button className="btn btn-primary" onClick={run} disabled={busy}>
            <Play size={15} /> {busy ? "Sending…" : "Run test"}
          </button>
        </div>
      }>
        <p className="muted small burst-explain">
          Sends {size} requests to <span className="mono">/api/health</span> at the same moment and reads the
          <span className="mono"> X-Served-By</span> header each server instance adds. {m.expect}
        </p>
        {!result ? (
          <div className="empty"><span className="empty-icon"><Play size={20} /></span>
            <div className="empty-title">Run the test to see which instances answer</div></div>
        ) : (
          <>
            <div className="burst-summary">
              <strong>{result.instances.length}</strong> instance{result.instances.length === 1 ? "" : "s"} answered{" "}
              <strong>{result.total - result.failed}</strong> requests in <strong>{(result.ms / 1000).toFixed(1)} s</strong>
              {result.failed > 0 && <span className="warn-text"> · {result.failed} failed</span>}
            </div>
            <ol className="bars">
              {result.instances.slice(0, TOP).map((x, i) => (
                <li key={x.id}>
                  <span className="bar-label">
                    <strong>{label(i)}</strong>
                    <span className="mono">{x.id}</span>
                  </span>
                  <span className="bar-track"><span className="bar-fill" style={{ width: `${(x.count / max) * 100}%` }} /></span>
                  <span className="bar-count">{x.count}</span>
                </li>
              ))}
            </ol>
            {result.instances.length > TOP && (() => {
              const rest = result.instances.slice(TOP);
              return (
                <p className="muted small bars-more">
                  + {rest.length} more instances answered the other {rest.reduce((n, x) => n + x.count, 0)} requests
                </p>
              );
            })()}
          </>
        )}
      </Card>
    </>
  );
}
