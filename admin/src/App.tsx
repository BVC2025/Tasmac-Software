import { useCallback, useEffect, useState, type ComponentType, type FormEvent, type SVGProps } from 'react'
import { BACKEND, login, RANK, setAuth, type User } from './api'
import machineImg from './assets/rvm-machine.jpg'
import {
  BellIcon, ChartIcon, GridIcon, ListIcon, LockIcon, LogoutIcon, MachineIcon, MessageIcon, QrIcon, ReceiptIcon,
  ScanIcon, ShieldIcon, TagIcon, UserIcon, UsersIcon,
} from './components/Icons'
import { PasswordInput } from './components/PasswordInput'
import { Account, Brands, fetchMe, Machines, Reports, Users } from './pages/Manage'
import { QrRegistry } from './pages/QrRegistry'
import { Alerts, Audit, Claims, Overview, Sessions, Sms, Transactions, type PageProps } from './pages/Operations'
import { usePoll } from './ui'

const VERSION = '0.3.0'
const TOKEN_KEY = 'rvm-admin-token'

const store = {
  get: () => {
    try {
      return sessionStorage.getItem(TOKEN_KEY) ?? ''
    } catch {
      return ''
    }
  },
  set: (t: string) => {
    try {
      if (t) sessionStorage.setItem(TOKEN_KEY, t)
      else sessionStorage.removeItem(TOKEN_KEY)
    } catch {
      /* private mode */
    }
  },
}

type Page = {
  key: string
  label: string
  subtitle: string
  icon: ComponentType<SVGProps<SVGSVGElement>>
  component: ComponentType<PageProps>
  min?: 'OPERATOR' | 'ADMIN'
  group: string
}

const PAGES: Page[] = [
  { key: 'overview', label: 'Dashboard', subtitle: 'Live status of the bottle return network', icon: GridIcon, component: Overview, group: 'Operations' },
  { key: 'alerts', label: 'Alerts', subtitle: 'Problems that need attention', icon: BellIcon, component: Alerts, group: 'Operations' },
  { key: 'transactions', label: 'Transactions', subtitle: 'Every ₹10 refund and its payout status', icon: ReceiptIcon, component: Transactions, group: 'Operations' },
  { key: 'sessions', label: 'Sessions', subtitle: 'Every bottle inserted, accepted or returned', icon: ListIcon, component: Sessions, group: 'Operations' },
  { key: 'claims', label: 'Refund QRs', subtitle: 'One-time-use status of each refund QR', icon: QrIcon, component: Claims, group: 'Operations' },
  { key: 'sms', label: 'SMS', subtitle: 'Refund confirmations sent to customers', icon: MessageIcon, component: Sms, group: 'Operations' },
  { key: 'reports', label: 'Reports', subtitle: 'Daily figures per machine, exportable to CSV', icon: ChartIcon, component: Reports, group: 'Operations' },
  { key: 'machines', label: 'Machines', subtitle: 'Registered RVMs, keys and status', icon: MachineIcon, component: Machines, group: 'Administration' },
  { key: 'qr-registry', label: 'QR registry', subtitle: 'Real bottle QRs accepted for the demo / pilot', icon: ScanIcon, component: QrRegistry, group: 'Administration' },
  { key: 'brands', label: 'Eligible brands', subtitle: 'Brands that qualify for the ₹10 refund', icon: TagIcon, component: Brands, group: 'Administration' },
  { key: 'users', label: 'Users & roles', subtitle: 'Portal accounts and permissions', icon: UsersIcon, component: Users, min: 'ADMIN', group: 'Administration' },
  { key: 'audit', label: 'Audit log', subtitle: 'Tamper-evident trail of every action', icon: ShieldIcon, component: Audit, group: 'Administration' },
]

function Wordmark({ light = false }: { light?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-white shadow-sm">
        <MachineIcon className="h-6 w-6 text-brand-700" />
      </span>
      <div className="leading-tight">
        <p className={`text-base font-extrabold tracking-wide ${light ? 'text-white' : 'text-brand-900'}`}>TASMAC RVM</p>
        <p className={`text-[11px] ${light ? 'text-white/60' : 'text-slate-500'}`}>Bottle Return Management</p>
      </div>
    </div>
  )
}

function Login({ onLogin }: { onLogin: (token: string, user: User) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const r = await login(username.trim(), password)
      onLogin(r.access_token, r.user)
    } catch (err) {
      setError((err as Error).message === 'Failed to fetch' ? `Cannot reach the server (${BACKEND})` : (err as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const field = 'w-full rounded-xl border border-slate-300 bg-white py-3 pl-11 text-[15px] text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-brand-600 focus:ring-4 focus:ring-brand-600/10 focus:outline-none md:py-4 md:text-lg tall:py-5 tall:pl-14 tall:text-xl'

  // Portrait (machine monitor 1080x1920, phones): image on top, form below.
  // Landscape desktop ("side:" variant): image and form side by side, 50 / 50.
  return (
    <div className="flex min-h-screen flex-col bg-white side:flex-row">
      {/* Hero */}
      <div className="relative h-[46vh] min-h-[360px] shrink-0 overflow-hidden tall:h-[50vh] side:h-auto side:min-h-0 side:w-1/2">
        <img src={machineImg} alt="TASMAC reverse vending machine in a retail outlet"
          className="absolute inset-0 h-full w-full object-cover object-[center_35%]" />
        <div className="absolute inset-0 bg-gradient-to-t from-brand-900 via-brand-900/55 to-brand-900/10 tall:via-brand-900/70" />
        <div className="absolute inset-x-0 top-0 h-36 bg-gradient-to-b from-brand-900/80 to-transparent" />
        <div className="absolute top-6 left-6 sm:top-8 sm:left-10 tall:top-12 tall:left-14 tall:scale-125 tall:origin-top-left"><Wordmark light /></div>
        <div className="absolute right-6 bottom-6 left-6 text-white sm:right-10 sm:bottom-10 sm:left-10 tall:right-14 tall:bottom-24 tall:left-14">
          <p className="mb-3 inline-block rounded-full bg-white/15 px-3 py-1 text-[11px] font-semibold tracking-wider uppercase backdrop-blur sm:text-xs tall:px-4 tall:py-1.5 tall:text-sm">
            Reverse Vending Machine Network
          </p>
          <h1 className="max-w-xl text-2xl leading-tight font-extrabold sm:text-4xl md:text-5xl tall:max-w-none tall:text-6xl side:text-4xl">
            Every bottle returned, every rupee accounted for.
          </h1>
          <p className="mt-3 max-w-xl text-sm text-white/80 sm:text-lg md:text-xl tall:mt-5 tall:max-w-none tall:text-2xl side:text-lg" lang="ta">
            பாட்டில்களை மறுசுழற்சிக்கு வழங்குங்கள் · தூய்மையான சூழல், பசுமையான எதிர்காலம்
          </p>
          <div className="mt-5 grid max-w-xl grid-cols-3 gap-2 text-xs sm:mt-8 sm:gap-4 sm:text-sm tall:mt-10 tall:max-w-none tall:gap-5 tall:text-lg">
            {[['₹10', 'Instant UPI refund'], ['1×', 'Each QR refunded once'], ['24×7', 'Live monitoring']].map(([v, l]) => (
              <div key={l} className="rounded-xl bg-white/10 p-3 backdrop-blur sm:p-4 tall:rounded-2xl tall:p-6">
                <p className="text-xl font-extrabold sm:text-2xl tall:text-4xl">{v}</p>
                <p className="text-white/70">{l}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Form */}
      <div className="relative z-10 flex flex-1 flex-col justify-between bg-white px-6 py-8 sm:px-10 tall:-mt-12 tall:rounded-t-[2.5rem] tall:px-20 tall:pt-16 tall:shadow-[0_-12px_40px_rgba(7,43,27,0.18)] side:w-1/2 side:px-14">
        <form onSubmit={submit} className="my-auto w-full max-w-md self-center py-6 md:max-w-lg tall:max-w-2xl side:max-w-md">
          <h2 className="text-3xl font-extrabold text-slate-900 md:text-4xl tall:text-5xl side:text-3xl">Sign in</h2>
          <p className="mt-2 text-slate-500 md:text-lg tall:mt-3 tall:text-xl side:text-base">Management portal for authorised TASMAC personnel.</p>

          <label className="mt-8 block text-sm font-semibold text-slate-700 md:text-base tall:mt-12 tall:text-lg" htmlFor="username">Username</label>
          <div className="relative mt-2">
            <UserIcon className="pointer-events-none absolute top-1/2 left-3.5 h-5 w-5 -translate-y-1/2 text-slate-400 tall:left-5 tall:h-6 tall:w-6" />
            <input id="username" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus
              autoComplete="username" placeholder="Enter your username" className={field} />
          </div>

          <label className="mt-5 block text-sm font-semibold text-slate-700 md:text-base tall:mt-7 tall:text-lg" htmlFor="password">Password</label>
          <div className="relative mt-2">
            <LockIcon className="pointer-events-none absolute top-1/2 left-3.5 z-10 h-5 w-5 -translate-y-1/2 text-slate-400 tall:left-5 tall:h-6 tall:w-6" />
            <PasswordInput id="password" value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password" placeholder="Enter your password" className={field} />
          </div>

          {error && <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 ring-1 ring-red-200">{error}</p>}

          <button disabled={busy || !username || !password}
            className="mt-7 w-full rounded-xl bg-brand-700 py-3.5 text-[15px] font-semibold text-white shadow-sm transition hover:bg-brand-600 disabled:opacity-50 md:py-4 md:text-lg tall:mt-10 tall:rounded-2xl tall:py-5 tall:text-xl">
            {busy ? 'Signing in…' : 'Sign in'}
          </button>

          <p className="mt-6 flex items-start gap-2 text-xs leading-relaxed text-slate-500 md:text-sm tall:mt-8 tall:text-base">
            <ShieldIcon className="mt-0.5 h-4 w-4 shrink-0" />
            Authorised users only. All sign-ins and actions are recorded in the audit log.
          </p>
        </form>
        <p className="text-center text-xs text-slate-400 tall:text-sm">TASMAC Reverse Vending Machine System · v{VERSION}</p>
      </div>
    </div>
  )
}

function AlertCount() {
  const { data } = usePoll<{ open_alerts: number }>('/stats')
  return data?.open_alerts ? (
    <span className="ml-auto min-w-6 rounded-full bg-red-500 px-1.5 text-center text-xs font-bold text-white">{data.open_alerts}</span>
  ) : null
}

function Clock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(id)
  }, [])
  const tz = { timeZone: 'Asia/Kolkata' } as const
  return (
    <span className="hidden text-right leading-tight md:block">
      <span className="block text-sm font-semibold text-slate-900 tabular-nums">
        {now.toLocaleTimeString('en-IN', { ...tz, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true }).toUpperCase()} IST
      </span>
      <span className="block text-xs text-slate-500">
        {now.toLocaleDateString('en-IN', { ...tz, weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' })}
      </span>
    </span>
  )
}

const initials = (name: string) => name.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase()

export default function App() {
  const [token, setToken] = useState(store.get)
  const [user, setUser] = useState<User | null>(null)
  const [page, setPage] = useState('overview')

  const logout = useCallback(() => {
    store.set('')
    setToken('')
    setUser(null)
    setPage('overview')
  }, [])

  // Token must be set before any child component polls
  if (token) setAuth(token, logout)

  useEffect(() => {
    if (token && !user) fetchMe().then(setUser).catch(logout)
  }, [token, user, logout])

  if (!token) {
    return <Login onLogin={(t, u) => { store.set(t); setAuth(t, logout); setToken(t); setUser(u) }} />
  }
  if (!user) return <div className="flex min-h-screen items-center justify-center text-slate-500">Loading…</div>

  const can = (role: 'OPERATOR' | 'ADMIN') => RANK[user.role] >= RANK[role]
  const visible = PAGES.filter((p) => !p.min || can(p.min))
  const current = visible.find((p) => p.key === page)
  const Page = current?.component

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-64 shrink-0 flex-col bg-brand-900 px-4 py-6 text-white">
        <div className="px-2"><Wordmark light /></div>
        <div className="mt-8 flex-1 overflow-y-auto">
          {['Operations', 'Administration'].map((g) => (
            <nav key={g} className="mb-6 flex flex-col gap-0.5">
              <p className="mb-1 px-3 text-[11px] font-semibold tracking-wider text-white/40 uppercase">{g}</p>
              {visible.filter((p) => p.group === g).map((p) => {
                const active = page === p.key
                return (
                  <button key={p.key} onClick={() => setPage(p.key)}
                    className={`group flex items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium transition ${
                      active ? 'bg-white text-brand-900 shadow-sm' : 'text-white/75 hover:bg-white/10 hover:text-white'}`}>
                    <p.icon className={`h-[18px] w-[18px] ${active ? 'text-brand-700' : 'text-white/60 group-hover:text-white'}`} />
                    {p.label}
                    {p.key === 'alerts' && <AlertCount />}
                  </button>
                )
              })}
            </nav>
          ))}
        </div>
        <button onClick={logout} className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-white/60 hover:bg-white/10 hover:text-white">
          <LogoutIcon className="h-[18px] w-[18px]" /> Sign out
        </button>
        <p className="mt-3 px-3 text-[11px] text-white/30">v{VERSION}</p>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center justify-between gap-4 border-b border-slate-200 bg-white/90 px-8 py-4 backdrop-blur">
          <div>
            <h1 className="text-xl font-bold text-slate-900">{page === 'account' ? 'My account' : current?.label}</h1>
            <p className="text-sm text-slate-500">{page === 'account' ? 'Profile and password' : current?.subtitle}</p>
          </div>
          <div className="flex items-center gap-5">
            <span className="hidden items-center gap-2 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-200 sm:flex">
              <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" /> Live
            </span>
            <Clock />
            <button onClick={() => setPage('account')} className="flex items-center gap-3 rounded-full py-1 pr-3 pl-1 hover:bg-slate-100">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-700 text-sm font-bold text-white">{initials(user.full_name)}</span>
              <span className="hidden text-left leading-tight sm:block">
                <span className="block text-sm font-semibold text-slate-900">{user.full_name}</span>
                <span className="block text-xs text-slate-500">{user.role.charAt(0) + user.role.slice(1).toLowerCase()}</span>
              </span>
            </button>
          </div>
        </header>
        <main className="flex-1 bg-slate-50 p-8">
          {page === 'account' ? <Account user={user} /> : Page && <Page can={can} go={setPage} />}
        </main>
      </div>
    </div>
  )
}
