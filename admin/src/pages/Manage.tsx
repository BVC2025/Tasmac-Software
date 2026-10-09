import { useState } from 'react'
import { download, get, patch, post, type Brand, type MachineRow, type Report, type Role, type ServiceWindow, type User } from '../api'
import { Badge, Btn, ErrorText, Field, inputCls, Modal, SecretBox, Table, fmtTime, rupees, usePoll } from '../ui'
import { PasswordInput } from '../components/PasswordInput'
import { BinBar, type PageProps } from './Operations'

// ---------------- machines ----------------

export function Machines({ can }: PageProps) {
  const { data, reload } = usePoll<MachineRow[]>('/machines')
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<MachineRow | null>(null)
  const [hoursFor, setHoursFor] = useState<MachineRow | null>(null)
  const [secret, setSecret] = useState<{ id: string; api_key: string } | null>(null)

  const rotate = async (id: string) => {
    if (!confirm(`Rotate API key for ${id}? The machine stops working until its config has the new key.`)) return
    setSecret(await post(`/machines/${id}/rotate-key`))
  }
  const toggle = async (m: MachineRow) => {
    if (m.active && !confirm(`Disable ${m.id}? It will be refused by the server immediately.`)) return
    await patch(`/machines/${m.id}`, { active: !m.active })
    reload()
  }

  return (
    <>
      {can('ADMIN') && <Btn className="mb-4" onClick={() => setAdding(true)}>+ Register machine</Btn>}
      <Table
        head={['Machine', 'Name', 'Location', 'Enabled', 'State', 'Service hours', 'Bin', 'Version', 'Last seen', '']}
        rows={(data ?? []).map((m) => [
          <b>{m.id}</b>, m.name, m.location ?? '—',
          m.active ? <span className="text-emerald-700">Yes</span> : <span className="text-red-600">Disabled</span>,
          <Badge value={m.state} />, <HoursText hours={m.service_hours} />, <BinBar pct={m.bin_fill_pct} />, m.software_version ?? '—', fmtTime(m.last_seen_at),
          <div className="flex gap-3">
            {can('OPERATOR') && <Btn variant="link" onClick={() => setEditing(m)}>Edit</Btn>}
            {can('OPERATOR') && <Btn variant="link" onClick={() => setHoursFor(m)}>Hours</Btn>}
            {can('OPERATOR') && <Btn variant="link" onClick={() => toggle(m)}>{m.active ? 'Disable' : 'Enable'}</Btn>}
            {can('ADMIN') && <Btn variant="link" onClick={() => rotate(m.id)}>Rotate key</Btn>}
          </div>,
        ])}
      />
      {adding && <MachineForm onClose={() => setAdding(false)} onCreated={(s) => { setSecret(s); reload() }} />}
      {editing && <MachineForm machine={editing} onClose={() => setEditing(null)} onCreated={() => reload()} />}
      {hoursFor && <ServiceHoursForm machine={hoursFor} onClose={() => setHoursFor(null)} onSaved={reload} />}
      {secret && (
        <Modal title={`API key for ${secret.id}`} onClose={() => setSecret(null)}>
          <SecretBox label="Shown only once. Put it in the machine config (backend.api_key)." value={secret.api_key} />
        </Modal>
      )}
    </>
  )
}

/** "10:00" -> "10:00 AM" */
const clock12 = (hhmm: string) => {
  const [h, m] = hhmm.split(':').map(Number)
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`
}

function HoursText({ hours }: { hours: ServiceWindow[] | null }) {
  if (!hours?.length) return <span className="text-slate-500">24 hours</span>
  return (
    <span className="text-xs leading-5">
      {hours.map((w) => <span key={w.start + w.end} className="block font-semibold">{clock12(w.start)} – {clock12(w.end)}</span>)}
    </span>
  )
}

/** When the machine takes bottles (India time). Outside these hours the kiosk shows "Closed". */
function ServiceHoursForm({ machine, onClose, onSaved }: { machine: MachineRow; onClose: () => void; onSaved: () => void }) {
  const [always, setAlways] = useState(!machine.service_hours?.length)
  const [windows, setWindows] = useState<ServiceWindow[]>(machine.service_hours?.length ? machine.service_hours : [{ start: '10:00', end: '22:00' }])
  const [err, setErr] = useState('')
  const set = (i: number, k: keyof ServiceWindow, v: string) => setWindows((ws) => ws.map((w, j) => (j === i ? { ...w, [k]: v } : w)))
  const save = async () => {
    try {
      await patch(`/machines/${machine.id}`, { service_hours: always ? [] : windows })
      onSaved()
      onClose()
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <Modal title={`Service hours · ${machine.id}`} onClose={onClose}>
      <div className="space-y-4">
        <p className="text-sm text-slate-500">
          India time, every day. Outside these hours the machine closes its inlet and the screen shows the opening hours.
          A customer already using the machine at closing time is always finished. The machine picks up a change within a minute.
        </p>
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input type="checkbox" checked={always} onChange={(e) => setAlways(e.target.checked)} className="h-4 w-4" />
          Open 24 hours
        </label>
        {!always && (
          <div className="space-y-2">
            {windows.map((w, i) => (
              <div key={i} className="flex items-end gap-2">
                <Field label="Opens"><input type="time" className={inputCls} value={w.start} onChange={(e) => set(i, 'start', e.target.value)} /></Field>
                <Field label="Closes"><input type="time" className={inputCls} value={w.end} onChange={(e) => set(i, 'end', e.target.value)} /></Field>
                {windows.length > 1 && (
                  <Btn variant="link" className="mb-2 text-red-700" onClick={() => setWindows((ws) => ws.filter((_, j) => j !== i))}>Remove</Btn>
                )}
              </div>
            ))}
            {windows.length < 4 && (
              <Btn variant="secondary" onClick={() => setWindows((ws) => [...ws, { start: '17:00', end: '21:00' }])}>+ Add another time</Btn>
            )}
            <p className="text-xs text-slate-500">Closing before opening (e.g. 22:00 → 02:00) means open past midnight.</p>
          </div>
        )}
        <ErrorText>{err}</ErrorText>
        <div className="flex justify-end gap-2 pt-2">
          <Btn variant="secondary" onClick={onClose}>Cancel</Btn>
          <Btn disabled={!always && windows.some((w) => !w.start || !w.end || w.start === w.end)} onClick={save}>Save</Btn>
        </div>
      </div>
    </Modal>
  )
}

function MachineForm({ machine, onClose, onCreated }: {
  machine?: MachineRow
  onClose: () => void
  onCreated: (s: { id: string; api_key: string }) => void
}) {
  const [id, setId] = useState(machine?.id ?? '')
  const [name, setName] = useState(machine?.name ?? '')
  const [location, setLocation] = useState(machine?.location ?? '')
  const [err, setErr] = useState('')
  const save = async () => {
    try {
      if (machine) {
        await patch(`/machines/${machine.id}`, { name, location: location || null })
        onCreated({ id: machine.id, api_key: '' })
      } else {
        onCreated(await post('/machines', { id: id.toUpperCase(), name, location: location || null }))
      }
      onClose()
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <Modal title={machine ? `Edit ${machine.id}` : 'Register machine'} onClose={onClose}>
      <div className="space-y-3">
        {!machine && (
          <Field label="Machine ID (e.g. RVM-CHN-0001)">
            <input className={inputCls} value={id} onChange={(e) => setId(e.target.value)} />
          </Field>
        )}
        <Field label="Name"><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Location / shop"><input className={inputCls} value={location} onChange={(e) => setLocation(e.target.value)} /></Field>
        <ErrorText>{err}</ErrorText>
        <div className="flex justify-end gap-2 pt-2">
          <Btn variant="secondary" onClick={onClose}>Cancel</Btn>
          <Btn disabled={!name || (!machine && !id)} onClick={save}>{machine ? 'Save' : 'Register'}</Btn>
        </div>
      </div>
    </Modal>
  )
}

// ---------------- brands ----------------

export function Brands({ can }: PageProps) {
  const { data, reload } = usePoll<Brand[]>('/brands', 0)
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [err, setErr] = useState('')
  const add = async () => {
    try {
      await post('/brands', { code: code.toUpperCase(), name })
      setCode('')
      setName('')
      setErr('')
      reload()
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <>
      <p className="mb-4 text-sm text-slate-500">
        Only bottles whose manufacturing QR carries an <b>active</b> brand code get a refund.
      </p>
      {can('ADMIN') && (
        <div className="mb-4 flex flex-wrap items-end gap-2">
          <Field label="Code"><input className={`${inputCls} w-28`} value={code} onChange={(e) => setCode(e.target.value)} /></Field>
          <Field label="Brand name"><input className={`${inputCls} w-64`} value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Btn disabled={!code || !name} onClick={add}>Add brand</Btn>
          <ErrorText>{err}</ErrorText>
        </div>
      )}
      <Table
        head={['Code', 'Name', 'Refund eligible', '']}
        rows={(data ?? []).map((b) => [
          <b>{b.code}</b>, b.name,
          b.active ? <span className="font-semibold text-emerald-700">Eligible</span> : <span className="text-red-600">Not eligible</span>,
          can('ADMIN') ? (
            <Btn variant="link" onClick={async () => { await patch(`/brands/${b.code}`, { active: !b.active }); reload() }}>
              {b.active ? 'Disable' : 'Enable'}
            </Btn>
          ) : null,
        ])}
      />
    </>
  )
}

// ---------------- reports ----------------

const isoDay = (d: Date) => d.toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })

export function Reports() {
  const today = new Date()
  const [from, setFrom] = useState(isoDay(new Date(today.getTime() - 6 * 864e5)))
  const [to, setTo] = useState(isoDay(today))
  const [machine, setMachine] = useState('')
  const params = new URLSearchParams({ from, to })
  if (machine) params.set('machine_id', machine)
  const { data, error } = usePoll<Report>(`/reports/daily?${params}`, 0)
  const { data: machines } = usePoll<MachineRow[]>('/machines', 0)
  const t = data?.totals
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <Field label="From"><input type="date" className={inputCls} value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label="To"><input type="date" className={inputCls} value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        <Field label="Machine">
          <select className={inputCls} value={machine} onChange={(e) => setMachine(e.target.value)}>
            <option value="">All machines</option>
            {(machines ?? []).map((m) => <option key={m.id} value={m.id}>{m.id}</option>)}
          </select>
        </Field>
        <Btn variant="secondary" onClick={() => download(`/reports/daily.csv?${params}`, `rvm-daily-${from}-to-${to}.csv`)}>
          ⬇ Download CSV
        </Btn>
      </div>
      <ErrorText>{error}</ErrorText>
      {t && (
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          {[['Bottles accepted', t.accepted], ['Bottles returned', t.returned], ['Refunds paid', t.paid], ['Amount paid', rupees(t.amount_paise)]].map(([l, v]) => (
            <div key={l as string} className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
              <p className="text-xs text-slate-500">{l}</p>
              <p className="mt-1 text-2xl font-bold">{v}</p>
            </div>
          ))}
        </div>
      )}
      <Table
        head={['Date (IST)', 'Machine', 'Sessions', 'Accepted', 'Returned', 'Refunds paid', 'Amount', 'Failed', 'Pending']}
        rows={(data?.rows ?? []).map((r) => [
          r.day, r.machine_id, r.sessions, r.accepted, r.returned, r.paid, rupees(r.amount_paise),
          r.failed ? <span className="text-red-600">{r.failed}</span> : 0, r.pending,
        ])}
        empty="No activity in this period"
      />
    </>
  )
}

// ---------------- users ----------------

export function Users() {
  const { data, reload } = usePoll<User[]>('/users', 0)
  const [form, setForm] = useState<User | 'new' | null>(null)
  return (
    <>
      <Btn className="mb-4" onClick={() => setForm('new')}>+ Add user</Btn>
      <p className="mb-4 text-sm text-slate-500">
        <b>VIEWER</b> reads everything · <b>OPERATOR</b> also resolves alerts, re-checks payouts, enables/disables machines ·
        <b> ADMIN</b> also manages users, machine keys and brands.
      </p>
      <Table
        head={['Username', 'Name', 'Role', 'Status', 'Last login', '']}
        rows={(data ?? []).map((u) => [
          <b>{u.username}</b>, u.full_name, <Badge value={u.role} />,
          !u.active ? <span className="text-red-600">Disabled</span>
            : u.locked_until && new Date(u.locked_until) > new Date() ? <span className="text-amber-600">Locked</span>
            : <span className="text-emerald-700">Active</span>,
          fmtTime(u.last_login_at),
          <Btn variant="link" onClick={() => setForm(u)}>Edit</Btn>,
        ])}
      />
      {form && <UserForm user={form === 'new' ? null : form} onClose={() => setForm(null)} onSaved={reload} />}
    </>
  )
}

function UserForm({ user, onClose, onSaved }: { user: User | null; onClose: () => void; onSaved: () => void }) {
  const [username, setUsername] = useState(user?.username ?? '')
  const [fullName, setFullName] = useState(user?.full_name ?? '')
  const [role, setRole] = useState<Role>(user?.role ?? 'VIEWER')
  const [active, setActive] = useState(user?.active ?? true)
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const save = async () => {
    try {
      if (user) await patch(`/users/${user.id}`, { full_name: fullName, role, active, ...(password ? { password } : {}) })
      else await post('/users', { username, full_name: fullName, role, password })
      onSaved()
      onClose()
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <Modal title={user ? `Edit ${user.username}` : 'Add user'} onClose={onClose}>
      <div className="space-y-3">
        {!user && <Field label="Username"><input className={inputCls} value={username} onChange={(e) => setUsername(e.target.value)} /></Field>}
        <Field label="Full name"><input className={inputCls} value={fullName} onChange={(e) => setFullName(e.target.value)} /></Field>
        <Field label="Role">
          <select className={inputCls} value={role} onChange={(e) => setRole(e.target.value as Role)}>
            <option value="VIEWER">VIEWER</option>
            <option value="OPERATOR">OPERATOR</option>
            <option value="ADMIN">ADMIN</option>
          </select>
        </Field>
        {user && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Active
          </label>
        )}
        <Field label={user ? 'Reset password (leave empty to keep)' : 'Password (min 10 chars, letters + numbers/symbols)'}>
          <PasswordInput className={inputCls} value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <ErrorText>{err}</ErrorText>
        <div className="flex justify-end gap-2 pt-2">
          <Btn variant="secondary" onClick={onClose}>Cancel</Btn>
          <Btn disabled={!fullName || (!user && (!username || !password))} onClick={save}>Save</Btn>
        </div>
      </div>
    </Modal>
  )
}

// ---------------- my account ----------------

export function Account({ user }: { user: User }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const save = async () => {
    setMsg('')
    setErr('')
    if (next !== repeat) return setErr('New passwords do not match')
    try {
      await post('/auth/password', { current_password: current, new_password: next })
      setMsg('Password changed')
      setCurrent('')
      setNext('')
      setRepeat('')
    } catch (e) {
      setErr((e as Error).message)
    }
  }
  return (
    <div className="max-w-sm space-y-3 rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
      <p className="text-sm text-slate-600">
        Signed in as <b>{user.username}</b> ({user.full_name}) <Badge value={user.role} />
      </p>
      <Field label="Current password"><PasswordInput className={inputCls} value={current} onChange={(e) => setCurrent(e.target.value)} /></Field>
      <Field label="New password"><PasswordInput className={inputCls} value={next} onChange={(e) => setNext(e.target.value)} /></Field>
      <Field label="Repeat new password"><PasswordInput className={inputCls} value={repeat} onChange={(e) => setRepeat(e.target.value)} /></Field>
      <ErrorText>{err}</ErrorText>
      {msg && <p className="text-sm text-emerald-700">{msg}</p>}
      <Btn disabled={!current || !next} onClick={save}>Change password</Btn>
    </div>
  )
}

export async function fetchMe() {
  return get<User>('/auth/me')
}
