import React, { useEffect, useState } from 'react'
import { PageHeader } from '../components/PageHeader'
import { mockAssetProvider } from '../assets/mockAssetProvider'
import type { AssetPreviewData, AssetPreviewProvider } from '../assets/types'
import { mockEmployeeProvider } from '../employees/mockEmployeeProvider'
import type { EmployeeDirectoryProvider } from '../employees/types'
import './settings.css'

type Section = 'general' | 'master-data' | 'access' | 'employee-sync' | 'notifications' | 'ai' | 'audit' | 'backup'
type SettingsProviders = { assetProvider?: AssetPreviewProvider; employeeProvider?: EmployeeDirectoryProvider }
const sections: { id: Section; label: string; requirement: string }[] = [
  { id: 'general', label: 'General', requirement: 'Application information' },
  { id: 'master-data', label: 'Master data', requirement: 'R-01, R-03' },
  { id: 'access', label: 'Users and permissions', requirement: 'R-17 preferred' },
  { id: 'employee-sync', label: 'Employee synchronization', requirement: 'Proposed direction' },
  { id: 'notifications', label: 'Notifications', requirement: 'R-12' },
  { id: 'ai', label: 'AI integration', requirement: 'Future integration' },
  { id: 'audit', label: 'Audit and security', requirement: 'R-11, R-17 preferred' },
  { id: 'backup', label: 'Backup and recovery', requirement: 'Operational service unavailable' },
]
type Preview = { assets: AssetPreviewData; departments: string[]; teams: string[]; designations: string[] }
function SettingCard({ title, status, children }: { title: string; status?: string; children: React.ReactNode }) {
  return <section className="settings-card"><div className="settings-card-heading"><h2>{title}</h2>{status && <span className="settings-state">{status}</span>}</div>{children}</section>
}
function DisabledControl({ children, explanation }: { children: React.ReactNode; explanation: string }) {
  return <div className="settings-disabled"><button type="button" disabled>{children}</button><span>{explanation}</span></div>
}
function SectionContent({ section, preview }: { section: Section; preview: Preview }) {
  if (section === 'general') return <>
    <SettingCard title="Application information" status="Available in this preview"><dl className="settings-facts"><div><dt>Application</dt><dd>Inventory AIOS</dd></div><div><dt>Interface</dt><dd>Web application preview</dd></div><div><dt>Configuration source</dt><dd>Static frontend preview</dd></div></dl><p className="settings-help">These are application labels, not configurable company preferences. No timezone, currency, numbering rule, or operational default is asserted.</p></SettingCard>
    <SettingCard title="Workspace preferences" status="Not configured"><p>No approved preference values are available.</p><DisabledControl explanation="Preference policies and saved configuration are not connected.">Edit preferences</DisabledControl></SettingCard>
  </>
  if (section === 'master-data') {
    const categories = [...new Set(preview.assets.products.map((product) => product.category))].sort()
    const locations = [...new Set(preview.assets.assets.map((asset) => asset.location))].sort()
    return <>
      <SettingCard title="Inventory-owned master data" status="Fictional preview"><div className="settings-master-grid"><div><h3>Asset categories</h3><ul>{categories.map((item) => <li key={item}>{item}</li>)}</ul>{categories.length === 0 && <p>No category preview is available.</p>}</div><div><h3>Locations</h3><ul>{locations.map((item) => <li key={item}>{item}</li>)}</ul>{locations.length === 0 && <p>No location preview is available.</p>}</div><div><h3>Suppliers</h3><p>Supplier records are unavailable in this preview.</p></div></div><DisabledControl explanation="Master-data create, edit, and delete operations are unavailable.">Manage inventory master data</DisabledControl></SettingCard>
      <SettingCard title="Employee-source organization data" status="Fictional employee preview"><div className="settings-master-grid"><div><h3>Departments</h3><ul>{preview.departments.map((item) => <li key={item}>{item}</li>)}</ul></div><div><h3>Teams</h3><ul>{preview.teams.map((item) => <li key={item}>{item}</li>)}</ul></div><div><h3>Designations</h3><ul>{preview.designations.map((item) => <li key={item}>{item}</li>)}</ul></div></div><p className="settings-help">Organization records are illustrative and proposed to remain owned by the authoritative employee source. No source connection exists.</p></SettingCard>
    </>
  }
  if (section === 'access') return <SettingCard title="Role and permission concepts" status="Proposed design only"><p>The requirements prefer login and role permissions (R-17), but do not define role names or authority boundaries. The documented role matrix is a proposal, not an active access list.</p><ul className="settings-role-list">{['Administrator', 'Inventory Officer', 'Approver', 'Employee', 'Auditor', 'Management'].map((role) => <li key={role}><strong>{role}</strong><span>Proposed role concept; assignments and effective permissions unavailable.</span></li>)}</ul><p className="settings-help">Application users and employee master records are separate. Frontend visibility is not authorization; protected access must be enforced by backend services.</p><DisabledControl explanation="Authentication, user records, assignments, and role administration are not operational here.">Manage users and roles</DisabledControl></SettingCard>
  if (section === 'employee-sync') return <SettingCard title="Employee source synchronization" status="Not connected"><dl className="settings-facts"><div><dt>Source connection</dt><dd>Not connected</dd></div><div><dt>Direction</dt><dd>Proposed one-way source to Inventory AIOS</dd></div><div><dt>Source mapping</dt><dd>Unavailable; source schema not verified</dd></div><div><dt>Last successful sync</dt><dd>Unavailable</dd></div><div><dt>Schedule</dt><dd>Not configured</dd></div><div><dt>Errors and conflicts</dt><dd>Unavailable</dd></div></dl><p className="settings-help">The employee source is a proposed authoritative system. No source database or credentials are configured in this frontend.</p><DisabledControl explanation="Connection testing and synchronization require source approval, verified mappings, and backend safeguards.">Test connection / Sync employees</DisabledControl></SettingCard>
  if (section === 'notifications') return <SettingCard title="Notification categories" status="Configuration unavailable"><p>R-12 identifies reminders for pending registration, pending returns, warranty expiration, pending approvals, and missing asset information.</p><ul className="settings-tag-list">{['Pending asset registration', 'Assets pending return', 'Warranty expiration', 'Pending approvals', 'Missing asset information'].map((item) => <li key={item}>{item}</li>)}</ul><p className="settings-help">Recipients, delivery channels, schedules, escalation, and individual preferences are unresolved.</p><DisabledControl explanation="No delivery service or scheduler is connected.">Configure notifications</DisabledControl></SettingCard>
  if (section === 'ai') return <SettingCard title="Grok AI integration" status="Not connected"><dl className="settings-facts"><div><dt>Planned provider</dt><dd>Grok (planned; not connected)</dd></div><div><dt>Availability</dt><dd>Unavailable</dd></div><div><dt>Model and credentials</dt><dd>Not configured</dd></div><div><dt>Capabilities</dt><dd>Future authorized assistance only</dd></div></dl><p className="settings-help">Future requests must pass through authorized backend services. AI must not receive unrestricted database access or approve sensitive actions without human confirmation and existing authorization.</p><DisabledControl explanation="No external AI service is called and no secret fields are exposed.">Configure AI integration</DisabledControl></SettingCard>
  if (section === 'audit') return <SettingCard title="Audit and security availability" status="Not operational"><p>The database audit foundation has been rehearsed, but runtime audit writing and audit viewing are not enabled.</p><ul className="settings-tag-list"><li>Before-and-after values: outstanding</li><li>Audit viewing and export permissions: unresolved</li><li>Retention policy: unresolved</li><li>Authentication provider and user mapping: unresolved</li><li>Runtime audit writer activation: pending</li></ul><DisabledControl explanation="This preview cannot change grants, permissions, or audit configuration.">Manage audit and security</DisabledControl></SettingCard>
  return <SettingCard title="Backup and recovery" status="Operational service unavailable"><p>Development backup and restore rehearsals are not a production backup service and do not establish production backup health.</p><p className="settings-help">Operational backup locations, schedules, timestamps, retention, and recovery guarantees are unavailable and are not displayed.</p><DisabledControl explanation="No backup or restore operation is connected to this page.">Back up / Restore</DisabledControl></SettingCard>
}

export function SettingsPage({ assetProvider = mockAssetProvider, employeeProvider = mockEmployeeProvider }: SettingsProviders = {}) {
  const [section, setSection] = useState<Section>('general')
  const [preview, setPreview] = useState<Preview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let current = true
    Promise.all([assetProvider.load(), Promise.resolve(employeeProvider)]).then(([assets, employees]) => {
      if (!current) return
      setPreview({ assets, departments: employees.departments.map((item) => item.name), teams: employees.teams.map((item) => item.name), designations: employees.designations.map((item) => item.name) })
      setError(false); setLoading(false)
    }).catch(() => { if (current) { setPreview(null); setError(true); setLoading(false) } })
    return () => { current = false }
  }, [assetProvider, employeeProvider, retry])
  function tabKey(event: React.KeyboardEvent<HTMLButtonElement>) {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const index = sections.findIndex((tab) => tab.id === section)
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? sections.length - 1 : (index + (['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : sections.length - 1)) % sections.length
    setSection(sections[next].id)
    document.getElementById('settings-tab-' + sections[next].id)?.focus()
  }
  return <>
    <PageHeader eyebrow="Administration" title="Settings" description="Review configuration boundaries and fictional reference-data previews. No administrative changes or external integrations are available." />
    <div className="settings-banner" role="status"><strong>Configuration preview</strong> - static design information and fictional master data only. No backend or external service is connected.</div>
    <div className="settings-layout">
      <nav className="settings-nav" aria-label="Settings sections" role="tablist" aria-orientation="vertical">{sections.map((tab) => <button id={'settings-tab-' + tab.id} key={tab.id} type="button" role="tab" aria-selected={section === tab.id} aria-controls="settings-panel" tabIndex={section === tab.id ? 0 : -1} onClick={() => setSection(tab.id)} onKeyDown={tabKey}><span>{tab.label}</span><small>{tab.requirement}</small></button>)}</nav>
      <section className="settings-content" id="settings-panel" role="tabpanel" aria-labelledby={'settings-tab-' + section}>
        {loading ? <p className="settings-message" role="status">Loading fictional configuration preview...</p> : error ? <div className="settings-message" role="alert"><strong>Configuration preview unavailable.</strong><p>A local reference provider failed. No live settings were requested.</p><button className="button workflow-secondary" type="button" onClick={() => { setLoading(true); setRetry((value) => value + 1) }}>Try again</button></div> : preview ? <SectionContent section={section} preview={preview} /> : <p className="settings-message">No preview information is available.</p>}
      </section>
    </div>
  </>
}
