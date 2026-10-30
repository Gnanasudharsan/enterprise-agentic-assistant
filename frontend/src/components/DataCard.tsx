import { useMemo, useState } from "react";

import type { Chart, TableResult } from "../api";
import { ChartIcon, CheckIcon, CodeIcon, CopyIcon, ShieldIcon, TableIcon } from "./Icons";

type Cell = string | number | boolean | null;
type View = "chart" | "table" | "sql";

const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)"];
const MAX_SERIES = SERIES.length; // more groups fold into small multiples elsewhere; we skip the chart

function humanize(col: string): string {
  const s = col.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function fmt(v: Cell): string {
  if (v === null) return "—";
  if (typeof v === "number") {
    if (Number.isInteger(v)) return v.toLocaleString();
    return v.toLocaleString(undefined, { maximumFractionDigits: 1 });
  }
  return String(v);
}

interface Series {
  name: string;
  values: (number | null)[];
}

/** Turns rows into x labels + series for one metric (optionally split by a group column). */
function shape(table: TableResult, chart: Chart, metric: string) {
  const col = (name: string) => table.columns.indexOf(name);
  const xi = col(chart.x);
  const yi = col(metric);
  const xs = [...new Set(table.rows.map((r) => String(r[xi])))];
  let series: Series[];
  if (chart.group) {
    const gi = col(chart.group);
    const groups = [...new Set(table.rows.map((r) => String(r[gi])))].sort();
    series = groups.map((g) => ({
      name: g,
      values: xs.map((x) => {
        const row = table.rows.find((r) => String(r[xi]) === x && String(r[gi]) === g);
        return row && typeof row[yi] === "number" ? (row[yi] as number) : null;
      }),
    }));
  } else {
    series = [{ name: humanize(metric), values: xs.map((x) => {
      const row = table.rows.find((r) => String(r[xi]) === x);
      return row && typeof row[yi] === "number" ? (row[yi] as number) : null;
    }) }]; // prettier-ignore
  }
  return { xs, series };
}

/** Round tick values (0, 2, 4, 6 rather than 0, 1.3, 2.5...) covering the data. */
function niceTicks(maxValue: number): number[] {
  const raw = Math.max(maxValue, 1e-9) / 4;
  const p = 10 ** Math.floor(Math.log10(raw));
  const n = raw / p;
  const step = (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
  const count = Math.max(1, Math.ceil(maxValue / step));
  return Array.from({ length: count + 1 }, (_, i) => i * step);
}

function ChartView({ table, chart }: { table: TableResult; chart: Chart }) {
  const [metric, setMetric] = useState(chart.y[0]);
  const [hover, setHover] = useState<number | null>(null);
  const { xs, series } = useMemo(() => shape(table, chart, metric), [table, chart, metric]);

  const W = 560;
  const H = 210;
  const pad = { l: 44, r: 12, t: 12, b: 26 };
  const iw = W - pad.l - pad.r;
  const ih = H - pad.t - pad.b;
  const ticks = niceTicks(Math.max(0, ...series.flatMap((s) => s.values.map((v) => v ?? 0))));
  const max = ticks[ticks.length - 1] || 1;
  const y = (v: number) => pad.t + ih - (v / max) * ih;
  const band = iw / xs.length;
  const cx = (i: number) => pad.l + band * i + band / 2;
  const isLine = chart.type === "line";
  const barGroup = Math.min(band * 0.7, 26 * series.length + 2 * (series.length - 1));
  const barW = (barGroup - 2 * (series.length - 1)) / series.length;
  const labelEvery = Math.ceil(xs.length / 8);

  return (
    <div className="viz">
      <div className="viz-controls">
        {chart.y.length > 1 && (
          <div className="seg" role="radiogroup" aria-label="Metric">
            {chart.y.map((m) => (
              <button key={m} type="button" role="radio" aria-checked={m === metric}
                className={m === metric ? "active" : ""} onClick={() => setMetric(m)}>
                {humanize(m)}
              </button>
            ))}
          </div>
        )}
        {series.length > 1 && (
          <div className="viz-legend">
            {series.map((s, i) => (
              <span key={s.name}>
                <span className="swatch" style={{ background: SERIES[i] }} />
                {s.name}
              </span>
            ))}
          </div>
        )}
        {chart.y.length === 1 && series.length === 1 && <span className="viz-title">{humanize(metric)}</span>}
      </div>
      <div className="viz-plot" onMouseLeave={() => setHover(null)}>
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${humanize(metric)} by ${humanize(chart.x)}`}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} className={t === 0 ? "axis" : "grid"} />
              <text x={pad.l - 8} y={y(t)} className="tick" textAnchor="end" dominantBaseline="middle">
                {fmt(t)}
              </text>
            </g>
          ))}
          {xs.map((x, i) =>
            i % labelEvery === 0 ? (
              <text key={x} x={cx(i)} y={H - 8} className="tick" textAnchor="middle">
                {x}
              </text>
            ) : null,
          )}
          {hover !== null && isLine && (
            <line x1={cx(hover)} x2={cx(hover)} y1={pad.t} y2={pad.t + ih} className="crosshair" />
          )}
          {isLine
            ? series.map((s, si) => {
                const pts = s.values
                  .map((v, i) => (v === null ? null : `${cx(i)},${y(v)}`))
                  .filter(Boolean)
                  .join(" ");
                return (
                  <g key={s.name}>
                    <polyline points={pts} fill="none" stroke={SERIES[si]} strokeWidth={2}
                      strokeLinejoin="round" strokeLinecap="round" />
                    {s.values.map((v, i) =>
                      v === null ? null : (
                        <circle key={i} cx={cx(i)} cy={y(v)} r={hover === i ? 5 : 4}
                          fill={SERIES[si]} className="dot" />
                      ),
                    )}
                  </g>
                );
              })
            : xs.map((_, i) =>
                series.map((s, si) => {
                  const v = s.values[i];
                  if (v === null) return null;
                  const x = cx(i) - barGroup / 2 + si * (barW + 2);
                  const h = Math.max(0, y(0) - y(v));
                  const r = Math.min(4, barW / 2, h);
                  // Rounded data end, square at the baseline.
                  const d = `M${x},${y(0)} V${y(v) + r} Q${x},${y(v)} ${x + r},${y(v)} H${x + barW - r} Q${x + barW},${y(v)} ${x + barW},${y(v) + r} V${y(0)} Z`;
                  return (
                    <path key={`${i}-${si}`} d={d} fill={SERIES[si]}
                      opacity={hover === null || hover === i ? 1 : 0.45} />
                  );
                }),
              )}
          {xs.map((x, i) => (
            <rect key={`hit-${x}`} x={pad.l + band * i} y={pad.t} width={band} height={ih}
              fill="transparent" onMouseEnter={() => setHover(i)} />
          ))}
        </svg>
        {hover !== null && (
          <div className="viz-tip" style={{ left: `${(cx(hover) / W) * 100}%` }}>
            <div className="viz-tip-x">{xs[hover]}</div>
            {series.map((s, si) => (
              <div key={s.name} className="viz-tip-row">
                <span className="swatch" style={{ background: SERIES[si] }} />
                <span>{series.length > 1 ? s.name : humanize(metric)}</span>
                <b>{fmt(s.values[hover])}</b>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function TableView({ table }: { table: TableResult }) {
  const [all, setAll] = useState(false);
  const rows = all ? table.rows : table.rows.slice(0, 8);
  const numeric = table.columns.map((_, i) => table.rows.every((r) => r[i] === null || typeof r[i] === "number"));
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {table.columns.map((c, i) => (
              <th key={c} className={numeric[i] ? "num" : undefined}>{humanize(c)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={ri}>
              {r.map((v, i) => (
                <td key={i} className={numeric[i] ? "num" : undefined}>{fmt(v)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {table.rows.length > 8 && (
        <button type="button" className="text-button" onClick={() => setAll((v) => !v)}>
          {all ? "Show fewer rows" : `Show all ${table.rows.length} rows`}
        </button>
      )}
    </div>
  );
}

function SqlView({ table }: { table: TableResult }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="sql-view">
      <button type="button" className="icon-button sql-copy" aria-label="Copy SQL"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(table.sql ?? "");
            setCopied(true);
            setTimeout(() => setCopied(false), 1400);
          } catch {
            // Clipboard blocked.
          }
        }}>
        {copied ? <CheckIcon width={14} height={14} /> : <CopyIcon width={14} height={14} />}
      </button>
      <pre><code>{table.sql}</code></pre>
      {table.attempts.length > 0 && (
        <div className="sql-attempts">
          <div className="sql-attempts-title">
            Rejected before this query ({table.attempts.length})
          </div>
          {table.attempts.map((a) => (
            <div key={a.attempt} className="sql-attempt">
              <span className="mono">#{a.attempt}</span> {a.error}
            </div>
          ))}
        </div>
      )}
      <p className="sql-note">
        <ShieldIcon width={13} height={13} /> Checked against the table and function allow-list,
        then run read-only as <span className="mono">analytics_reader</span> with a time and row limit.
      </p>
    </div>
  );
}

export function DataCard({ table, id, cited }: { table: TableResult; id: string; cited: boolean }) {
  const chartable = !!table.chart && (!table.chart.group || new Set(table.rows.map((r) => r[table.columns.indexOf(table.chart!.group!)])).size <= MAX_SERIES);
  const [view, setView] = useState<View>(chartable ? "chart" : "table");

  if (table.error) {
    return (
      <div className="data-card data-card-failed" id={id}>
        <div className="data-head">
          <span className="data-index warn">!</span>
          <div className="data-head-text">
            <div className="data-title">{table.title}</div>
            <div className="data-sub">{table.error}</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`data-card ${cited ? "cited" : ""}`} id={id}>
      <div className="data-head">
        <span className="data-index">T{table.index}</span>
        <div className="data-head-text">
          <div className="data-title">{table.title}</div>
          <div className="data-sub">
            <span className={`origin origin-${table.origin}`}>
              {table.origin === "certified" ? "Reviewed query" : "Generated SQL"}
            </span>
            {table.row_count} row{table.row_count === 1 ? "" : "s"}
            {table.truncated && " (truncated)"} · {table.elapsed_ms} ms
          </div>
        </div>
        <div className="seg seg-icons" role="tablist" aria-label="View">
          {chartable && (
            <button type="button" role="tab" aria-selected={view === "chart"} className={view === "chart" ? "active" : ""} onClick={() => setView("chart")} title="Chart">
              <ChartIcon width={14} height={14} />
            </button>
          )}
          <button type="button" role="tab" aria-selected={view === "table"} className={view === "table" ? "active" : ""} onClick={() => setView("table")} title="Table">
            <TableIcon width={14} height={14} />
          </button>
          <button type="button" role="tab" aria-selected={view === "sql"} className={view === "sql" ? "active" : ""} onClick={() => setView("sql")} title="SQL">
            <CodeIcon width={14} height={14} />
          </button>
        </div>
      </div>
      <div className="data-body">
        {view === "chart" && chartable && <ChartView table={table} chart={table.chart!} />}
        {view === "table" && <TableView table={table} />}
        {view === "sql" && <SqlView table={table} />}
      </div>
    </div>
  );
}
