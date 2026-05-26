'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { 
  LayoutDashboard, 
  CheckSquare, 
  Settings, 
  Briefcase, 
  FileEdit,
  FolderOpen,
  PanelLeftClose,
  Activity,
  LogOut
} from 'lucide-react'
import { User } from '@/lib/mocks/rfpData'

export function Sidebar({ onToggle }: { onToggle?: () => void }) {
  const pathname = usePathname()
  const router = useRouter()
  const [user, setUser] = useState<User | null>(null)

  useEffect(() => {
    const stored = localStorage.getItem('rfp_user')
    if (stored) {
      setUser(JSON.parse(stored))
    } else {
      router.push('/login')
    }
  }, [router])

  if (!user) return <div className="w-56 border-r border-zinc-200 bg-white h-screen" />

  const isPM = user.role === 'pm'

  const pmLinks = [
    { name: 'Dashboard', href: '/dashboard/ceo', icon: LayoutDashboard },
    { name: 'Approvals', href: '/dashboard/ceo/approvals', icon: CheckSquare },
    { name: 'Settings', href: '/dashboard/ceo/settings', icon: Settings },
  ]

  const architectLinks = [
    { name: 'Assigned RFPs', href: '/dashboard/architect', icon: Briefcase },
    { name: 'Workspace', href: '/dashboard/architect/workspace', icon: FolderOpen },
    { name: 'Settings', href: '/dashboard/architect/settings', icon: Settings },
  ]

  const links = isPM ? pmLinks : architectLinks

  return (
    <div className="h-full flex flex-col py-5 px-3.5 bg-white border-r border-zinc-200/60 relative overflow-hidden">
      <div className="mb-8 flex items-center justify-between px-1">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-zinc-900 rounded-lg flex items-center justify-center shadow-sm">
            <span className="text-white font-black text-xs italic">R</span>
          </div>
          <div className="flex flex-col">
            <span className="text-[11px] font-bold text-zinc-900 leading-tight uppercase tracking-widest">
              {isPM ? 'Manager' : 'Architect'}
            </span>
            <span className="text-[10px] text-zinc-400 font-medium truncate max-w-[80px]">{user.name}</span>
          </div>
        </div>
        <button
          onClick={onToggle}
          className="p-1.5 rounded-lg hover:bg-zinc-100 text-zinc-400 hover:text-zinc-900 transition-all active:scale-95"
          title="Collapse"
        >
          <PanelLeftClose className="w-3.5 h-3.5" />
        </button>
      </div>

      <nav className="flex-1 space-y-1">
        {links.map((link) => {
          const isActive = pathname === link.href || pathname.startsWith(link.href + '/')
          const Icon = link.icon
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] transition-all group ${
                isActive
                  ? 'bg-zinc-100 text-zinc-900 font-bold shadow-sm border border-zinc-200/20'
                  : 'text-zinc-500 hover:text-zinc-900 hover:bg-zinc-50 font-medium'
              }`}
            >
              <Icon className={`w-4 h-4 transition-colors ${isActive ? 'text-zinc-900' : 'text-zinc-400 group-hover:text-zinc-900'}`} />
              {link.name}
            </Link>
          )
        })}
      </nav>

      {isPM && <QuotaIndicator />}

      <div className="mt-4 pt-4 border-t border-zinc-100">
        <button
          onClick={() => {
            localStorage.removeItem('rfp_user')
            router.push('/login')
          }}
          className="w-full flex items-center justify-center gap-2 py-2 text-[11px] font-bold text-zinc-500 hover:text-rose-600 border border-zinc-200 hover:border-rose-100 rounded-lg hover:bg-rose-50/30 transition-all uppercase tracking-widest"
        >
          <LogOut className="w-3 h-3" />
          Sign Out
        </button>
      </div>
    </div>
  )
}

function QuotaIndicator() {
  const [quota, setQuota] = useState<{request_count: number, token_count: number, is_exhausted: boolean, health: string} | null>(null)

  useEffect(() => {
    async function fetchQuota() {
      try {
        const { fetchApi } = await import('@/lib/api')
        const data = await fetchApi('/ai/quota-status')
        setQuota(data)
      } catch (e) {
        console.error("Failed to fetch quota", e)
      }
    }
    fetchQuota()
    const interval = setInterval(fetchQuota, 30000)
    return () => clearInterval(interval)
  }, [])

  if (!quota) return null

  const formatTokens = (n: number) => {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M'
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
    return n.toString()
  }

  return (
    <div className="mt-4">
      <div className="p-3.5 rounded-xl border border-zinc-100 bg-zinc-50/50">
        <div className="flex items-center justify-between mb-2.5">
          <div className="flex items-center gap-2">
            <Activity className="w-3 h-3 text-zinc-400" />
            <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">Usage</span>
          </div>
          <span className={`text-[9px] font-black uppercase px-1.5 py-0.5 rounded ${quota.health === 'Good' ? 'text-emerald-600 bg-emerald-50' : quota.health === 'Warning' ? 'text-amber-600 bg-amber-50' : 'text-rose-600 bg-rose-50'}`}>
            {quota.health}
          </span>
        </div>
        
        <div className="space-y-2">
          <div className="w-full bg-zinc-200 h-1 rounded-full overflow-hidden">
            <div 
              className={`h-full transition-all duration-700 ${quota.health === 'Good' ? 'bg-zinc-900' : quota.health === 'Warning' ? 'bg-amber-500' : 'bg-rose-500'}`}
              style={{ width: `${Math.min((quota.token_count / 2000000) * 100, 100)}%` }}
            />
          </div>
          <div className="flex justify-between text-[10px] font-bold text-zinc-500">
             <span className="text-zinc-900">{formatTokens(quota.token_count)} <span className="text-zinc-400 font-medium">/ 2M</span></span>
             <span className="text-zinc-400">{quota.request_count} req</span>
          </div>
        </div>
      </div>
    </div>
  )
}
