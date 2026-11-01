import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'

type Json = Record<string, unknown>
type ListResponse = { items: Json[]; limit: number; offset: number }
type Module = 'portfolio' | 'countries' | 'credits' | 'risk' | 'quality' | 'forecast' | 'research' | 'operations'
const MODULES: { id: Module; label: string; group: string }[] = [
  { id: 'portfolio', label: 'Command Center', group: 'FINANCIAL INTELLIGENCE' },
  { id: 'countries', label: 'Country & Project Explorer', group: 'FINANCIAL INTELLIGENCE' },
  { id: 'credits', label: 'Credit Intelligence', group: 'FINANCIAL INTELLIGENCE' },
  { id: 'risk', label: 'Risk Watchlist', group: 'FINANCIAL INTELLIGENCE' },
  { id: 'quality', label: 'Data Quality Center', group: 'COMING IN LATER PHASES' },
  { id: 'forecast', label: 'Forecast Studio', group: 'COMING IN LATER PHASES' },
  { id: 'research', label: 'Research Laboratory', group: 'COMING IN LATER PHASES' },
  { id: 'operations', label: 'Operations Center', group: 'COMING IN LATER PHASES' },
]
const text = (v: unknown) => v === null || v === undefined ? '—' : String(v)
function money(v: unknown): string {
  if (v === null || v === undefined) return '—'
  const s = String(v)
  if (!/^-?\d+(\.\d+)?$/.test(s)) return s
  const [head, fraction] = s.split('.')
  return '$' + head.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (fraction ? '.' + fraction : '')
}
function Field({ label, value }: { label: string; value: unknown }) {
  return <div className="stat"><span>{label}</span><strong title={text(value)}>{text(value)}</strong></div>
}
function MoneyField({ label, value }: { label: string; value: unknown }) {
  return <div className="stat"><span>{label}</span><strong title={money(value)}>{money(value)}</strong></div>
}
function Table({ rows, columns, onSelect }: { rows: Json[]; columns: [string, string, ((v: unknown) => string)?][]; onSelect?: (v: Json) => void }) {
  if (!rows.length) return <p className="empty">No matching records in the current dataset.</p>
  return <div className="table-wrap"><table><thead><tr>{columns.map(([key, label]) => <th key={key}>{label}</th>)}</tr></thead>
    <tbody>{rows.map((row, i) => <tr key={String(row.credit_snapshot_id ?? row.credit_id ?? row.project_pk ?? row.country_id ?? i)}
      onClick={() => onSelect?.(row)} className={onSelect ? 'clickable' : ''}>
      {columns.map(([key, , render]) => <td key={key}>{render ? render(row[key]) : text(row[key])}</td>)}</tr>)}</tbody></table></div>
}
const Column = (key: string, label: string, render?: (v: unknown) => string): [string, string, ((v: unknown) => string)?] => [key, label, render]

export default function App() {
  const [token, setToken] = useState('')
  const [role, setRole] = useState('')
  const [loginUser, setLoginUser] = useState('analyst')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [module, setModule] = useState<Module>('portfolio')
  const [summary, setSummary] = useState<Json | null>(null)
  const [countries, setCountries] = useState<Json[]>([])
  const [projects, setProjects] = useState<Json[]>([])
  const [credits, setCredits] = useState<Json[]>([])
  const [risk, setRisk] = useState<Json[]>([])
  const [search, setSearch] = useState('')
  const [countryId, setCountryId] = useState<number | null>(null)
  const [projectPk, setProjectPk] = useState<number | null>(null)
  const [creditId, setCreditId] = useState<number | null>(null)
  const [timeline, setTimeline] = useState<Json[]>([])
  const [lineage, setLineage] = useState<Json | null>(null)
  const [selectedPeriod, setSelectedPeriod] = useState('')
  const listRequest = useRef(0)
  const timelineRequest = useRef(0)
  const lineageRequest = useRef(0)

  // Changing scope must invalidate both outstanding requests and the displayed detail.
  const clearCreditDetail = () => {
    listRequest.current += 1
    timelineRequest.current += 1
    lineageRequest.current += 1
    setCreditId(null)
    setTimeline([])
    setLineage(null)
    setSelectedPeriod('')
  }

  const request = useCallback(async <T,>(url: string, credential = token): Promise<T> => {
    const response = await fetch(url, { headers: { Authorization: `Bearer ${credential}` }, cache: 'no-store' })
    if (response.status === 401) { setToken(''); throw new Error('Session expired. Sign in again.') }
    if (!response.ok) { const payload = await response.json().catch(() => ({}));
      throw new Error(typeof payload.detail === 'string' ? payload.detail : `HTTP ${response.status}`) }
    return response.json() as Promise<T>
  }, [token])

  const load = useCallback(async () => {
    if (!token) return
    const sequence = ++listRequest.current
    setBusy(true); setError('')
    try {
      if (module === 'portfolio') {
        const result = await request<Json>('/api/v1/portfolio/summary')
        if (listRequest.current === sequence) setSummary(result)
      }
      if (module === 'countries') {
        const qs = encodeURIComponent(search)
        const [c, p] = await Promise.all([
          request<ListResponse>(`/api/v1/countries?limit=100&q=${qs}`),
          request<ListResponse>(`/api/v1/projects?limit=100&q=${qs}${countryId ? `&country_id=${countryId}` : ''}`),
        ])
        if (listRequest.current === sequence) { setCountries(c.items); setProjects(p.items) }
      }
      if (module === 'credits') {
        const c = await request<ListResponse>(`/api/v1/credits?limit=100&q=${encodeURIComponent(search)}${projectPk ? `&project_pk=${projectPk}` : ''}`)
        if (listRequest.current === sequence) setCredits(c.items)
      }
      if (module === 'risk') {
        const result = await request<{ items: Json[] }>('/api/v1/risk/watchlist?limit=100')
        if (listRequest.current === sequence) setRisk(result.items)
      }
    } catch (e) {
      if (listRequest.current === sequence) setError(e instanceof Error ? e.message : 'Unexpected API error')
    } finally {
      if (listRequest.current === sequence) setBusy(false)
    }
  }, [token, module, request, search, countryId, projectPk])

  useEffect(() => { void load() }, [load])

  const openCredit = async (id: number) => {
    // Only the newest selection may publish a timeline or error.
    const sequence = ++timelineRequest.current
    lineageRequest.current += 1
    setCreditId(id); setTimeline([]); setModule('credits'); setSearch(''); setError(''); setLineage(null); setSelectedPeriod('')
    try {
      const result = await request<{ items: Json[] }>(`/api/v1/credits/${id}/timeline?limit=250`)
      if (timelineRequest.current === sequence) setTimeline([...result.items].reverse())
    } catch (e) {
      if (timelineRequest.current === sequence) { setError(e instanceof Error ? e.message : 'Unable to load credit'); setTimeline([]) }
    }
  }
  const showLineage = async (period: string) => {
    if (!creditId) return
    const chosenCreditId = creditId
    const sequence = ++lineageRequest.current
    setSelectedPeriod(period); setLineage(null); setError('')
    try {
      const result = await request<{ item: Json }>(`/api/v1/credits/${chosenCreditId}/lineage?period=${encodeURIComponent(period)}`)
      if (lineageRequest.current === sequence) setLineage(result.item)
    } catch (e) {
      if (lineageRequest.current === sequence) setError(e instanceof Error ? e.message : 'Unable to fetch lineage')
    }
  }
  const login = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setError('')
    try { const res = await fetch('/api/v1/auth/token', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: loginUser, password }), cache: 'no-store' })
      if (!res.ok) throw new Error(res.status === 429 ? 'Too many attempts; try again later.' : 'Invalid credentials')
      const body = await res.json() as { access_token: string }
      const userRes = await fetch('/api/v1/auth/me', { headers: { Authorization: `Bearer ${body.access_token}` } })
      if (!userRes.ok) throw new Error('Unable to verify session')
      const user = await userRes.json() as { username: string; role: string }
      setRole(user.role); setToken(body.access_token); setPassword('')
    } catch (e) { setError(e instanceof Error ? e.message : 'Sign in failed') } finally { setBusy(false) }
  }
  if (!token) return <div className="login-layout"><div className="login-hero"><div className="logomark">F<span>W</span></div>
    <p className="eyebrow">WORLD BANK FINANCIAL OBSERVATIONS</p><h1>Financial intelligence,<br/>with traceable evidence.</h1>
    <p>Explore credit-level historical balances, investigate missing periods, and inspect source provenance.</p>
    <div className="hero-foot">FLOWWATCH <span>V7 / ANALYST WORKSPACE</span></div></div>
    <form className="login-card" onSubmit={e => void login(e)}><p className="eyebrow">SECURE ACCESS</p><h2>Sign in to FlowWatch</h2>
    <p className="muted">Local pilot identity. Access requires configured credentials.</p>
    <label>Username<input value={loginUser} maxLength={80} autoComplete="username" onChange={e => setLoginUser(e.target.value)} /></label>
    <label>Password<input type="password" value={password} autoComplete="current-password" onChange={e => setPassword(e.target.value)} /></label>
    {error && <div className="error" role="alert">{error}</div>}
    <button disabled={busy || !password} type="submit">{busy ? 'Authenticating…' : 'Sign in'}</button>
    <p className="tiny">No production identity federation configured. Access tokens remain in memory.</p></form></div>

  return <div className="workspace"><aside className="sidebar"><div className="brand"><div className="mark">F<span>W</span></div><div><strong>FlowWatch</strong><small>FINANCIAL INTELLIGENCE</small></div></div>
    <nav>{Array.from(new Set(MODULES.map(m => m.group))).map(group => <div key={group}><p className="navgroup">{group}</p>
      {MODULES.filter(m => m.group === group).map(m => <button key={m.id} className={`nav-item ${module === m.id ? 'active' : ''}`}
        onClick={() => { setModule(m.id); setError(''); setSearch('') }}><span className="nav-dot"/>{m.label}{m.group.includes('LATER') && <span className="soon">PLANNED</span>}</button>)}</div>)}</nav>
    <div className="sidebar-foot"><div className="status-pill"><span className="status-dot"/> ANALYST SESSION</div><p>Read-only • Isolated warehouse</p></div></aside>
    <div className="main"><header className="topbar"><div><span className="topbar-crumb">FLOWWATCH / V7 / DAY 2</span><h2>{MODULES.find(m => m.id === module)?.label}</h2></div>
      <div className="top-actions"><span className="role">{role.toUpperCase()}</span><button className="subtle" onClick={() => {setToken('');setRole('');setProjectPk(null);setCountryId(null);clearCreditDetail()}}>Sign out</button></div></header>
      <div className="content"><div className="section-heading"><div><p className="eyebrow">FINANCIAL OBSERVATION PLATFORM</p><h1>{module === 'portfolio' ? 'Portfolio Command Center' : MODULES.find(m => m.id === module)?.label}</h1>
        <p>Source-backed World Bank financial records from the isolated dbt warehouse.</p></div>
        {module === 'portfolio' && <button className="outline" onClick={() => void load()}>Refresh data</button>}</div>
      {error && <div className="error" role="alert">{error}</div>}
      {busy && <div className="loading">Loading warehouse records…</div>}
      {module === 'portfolio' && <><div className="metric-grid"><Field label="Credits" value={summary?.credits} /><Field label="Projects" value={summary?.projects} />
        <Field label="Countries" value={summary?.countries} /><Field label="Latest reporting date" value={summary?.latest_period} /></div>
        <div className="grid-two"><div className="panel"><div className="panel-title"><h3>Portfolio financial balances</h3><span>USD • LATEST PER CREDIT</span></div>
          <div className="stacked-stats"><MoneyField label="Original principal" value={summary?.original_principal_usd}/>
          <MoneyField label="Reported disbursed" value={summary?.reported_disbursed_usd}/>
          <MoneyField label="Reported undisbursed" value={summary?.reported_undisbursed_usd}/>
          <MoneyField label="Reported cancelled" value={summary?.reported_cancelled_usd}/></div></div>
          <div className="panel"><div className="panel-title"><h3>Reporting integrity</h3><span>CONTRACT</span></div>
          <div className="insight"><strong>Period-end stocks</strong><p>Values reflect the latest available observation for each credit, not synchronized as-of portfolio cash flows.</p></div>
          <div className="insight"><strong>Mixed latest dates</strong><p>Earliest credit latest period: {text(summary?.earliest_latest_period)}. Latest: {text(summary?.latest_period)}.</p></div>
          <div className="insight"><strong>Inspectable provenance</strong><p>Every available credit observation exposes run ID, checksum, and record key.</p></div></div></div></>}
      {module === 'countries' && <><div className="filters"><input placeholder="Search countries or projects" value={search} onChange={e=>setSearch(e.target.value)}/>
          <button className="outline" onClick={() => {setCountryId(null);setProjectPk(null);clearCreditDetail();setProjects([])}}>All countries</button></div>
        <div className="panel"><div className="panel-title"><h3>Countries</h3><span>SELECT TO FILTER PROJECTS</span></div>
          <Table rows={countries} columns={[Column('country_code','Code'),Column('country_name','Country'),Column('region_name','Region'),Column('credits','Credits'),Column('reported_disbursed_usd','Reported disbursed',money)]}
            onSelect={r => {setCountryId(Number(r.country_id));setProjectPk(null);clearCreditDetail();setProjects([])}}/>{countryId && <p className="selection">Selected country ID: {countryId}</p>}</div>
        <div className="panel"><div className="panel-title"><h3>Projects</h3><span>SELECT TO EXPLORE CREDITS</span></div>
          <Table rows={projects} columns={[Column('project_id','Project ID'),Column('project_name','Name'),Column('country_name','Country'),Column('credits','Credits'),Column('reported_disbursed_usd','Reported disbursed',money)]}
            onSelect={r=>{setProjectPk(Number(r.project_pk));clearCreditDetail();setCredits([]);setModule('credits');setSearch('')}} /></div></>}
      {module === 'credits' && <><div className="filters"><input placeholder="Search credit numbers" value={search} onChange={e=>{setSearch(e.target.value);clearCreditDetail();setCredits([])}}/>
          {projectPk && <button className="outline" onClick={()=>{setProjectPk(null);clearCreditDetail();setCredits([])}}>Clear project {projectPk}</button>}</div>
        <div className="panel"><div className="panel-title"><h3>Credit directory</h3><span>SELECT CREDIT FOR HISTORY</span></div>
          <Table rows={credits} columns={[Column('credit_number','Credit'),Column('project_id','Project'),Column('country_name','Country'),Column('latest_period','Latest period'),Column('reported_disbursed_usd','Reported disbursed',money)]}
            onSelect={r=>void openCredit(Number(r.credit_id))} /></div>
        {creditId && <div className="panel"><div className="panel-title"><h3>Credit #{creditId} · Monthly history</h3><span>{timeline.length} OBSERVATIONS LOADED</span></div>
          <p className="muted">Balance changes only appear for consecutive periods. Click a row to inspect source provenance.</p>
          <Table rows={timeline} columns={[Column('end_of_period','Reporting date'),Column('disbursed_amount_usd','Reported disbursed',money),
            Column('undisbursed_amount_usd','Undisbursed',money),Column('change_in_reported_disbursed_usd','Balance change',money),
            Column('is_consecutive_month','Previous month adjacent',v=>v?'Yes':'No')]}
            onSelect={r=>void showLineage(String(r.end_of_period))}/>
          {lineage && <div className="lineage"><p className="eyebrow">SOURCE LINEAGE · {selectedPeriod}</p>
            <div className="details"><Field label="Ingestion run" value={lineage.ingestion_run_id}/><Field label="Source record key" value={lineage.source_record_key}/>
            <Field label="SHA-256 checksum" value={lineage.source_checksum}/><Field label="Canonical snapshot" value={lineage.credit_snapshot_id}/></div>
            <p className="tiny">Warehouse-to-canonical locator only; independent MongoDB source-page verification occurs in the operator workflow.</p></div>}</div>}</>}
      {module === 'risk' && <><div className="notice"><strong>Descriptive financial signals, not predictions.</strong> Reporting gaps and unchanged balances are investigation prompts, not confirmed credit risk or cash-flow events.</div>
        <div className="panel"><div className="panel-title"><h3>Credit observation watchlist</h3><span>RULE-BASED</span></div>
        <Table rows={risk} columns={[Column('credit_number','Credit'),Column('latest_period','Latest period'),Column('reporting_gaps','Reporting gaps'),
          Column('unchanged_consecutive_periods','Unchanged months'),Column('negative_balance_changes','Negative changes')]}
          onSelect={r=>{setProjectPk(null);setCredits([]);void openCredit(Number(r.credit_id))}}/></div></>}
      {['quality','forecast','research','operations'].includes(module) && <div className="panel planned"><div className="planned-icon">◇</div><h3>Integration scheduled for a later sprint phase</h3>
        <p>{module === 'quality' ? 'The source reconciliation and quarantine data already exist; the interactive operator workflow is not yet integrated.' :
          module === 'forecast' ? 'This module will connect only after temporally valid baselines, training eligibility and calibrated predictions have been verified.' :
          module === 'research' ? 'Experiment lineage, maturity ledgers and uncertainty evaluation will be added during the ML research phase.' :
          'Airflow, service health, model governance and operational monitoring will be integrated in subsequent phases.'}</p></div>}
      <footer className="footer">FLOWWATCH V7 · HISTORICAL FINANCIAL OBSERVATIONS · NOT VERIFIED CASH FLOWS OR ML PREDICTIONS</footer></div></div></div>
}
