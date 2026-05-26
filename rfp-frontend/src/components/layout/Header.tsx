'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { Bell, Search, LogOut, User as UserIcon, Settings as SettingsIcon, PanelLeftOpen } from 'lucide-react'
import { User } from '@/lib/mocks/rfpData'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Input } from '@/components/ui/input'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuItem,
} from '@/components/ui/dropdown-menu'
import { useRouter } from 'next/navigation'
import { cn } from '@/lib/utils'
import { formatNotificationTime } from '@/lib/dateUtils'

interface HeaderProps {
  showSidebarToggle?: boolean
  onSidebarToggle?: () => void
}

// Global refetch trigger — pages can call window.__refetchNotifications?.() after lifecycle actions
declare global {
  interface Window {
    __refetchNotifications?: () => void
  }
}

export function Header({ showSidebarToggle, onSidebarToggle }: HeaderProps) {
  const router = useRouter()
  const [user, setUser] = useState<User | null>(null)
  const [notifications, setNotifications] = useState<any[]>([])
  // unreadCount drives the badge — never zeroed just by opening the dropdown
  const [unreadCount, setUnreadCount] = useState(0)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchNotifications = useCallback(async () => {
    try {
      const { fetchApi } = await import('@/lib/api')
      // FIX: Fetch latest 10 — read AND unread — so dropdown always shows content
      const data: any[] = await fetchApi('/rfps/notifications')
      setNotifications(data || [])
      // Badge count is derived from actual data, not a separate boolean that gets cleared on open
      setUnreadCount((data || []).filter((n: any) => !n.is_read).length)
    } catch (e) {
      console.error('Failed to fetch notifications', e)
    }
  }, [])

  useEffect(() => {
    const stored = localStorage.getItem('rfp_user')
    if (stored) setUser(JSON.parse(stored))

    fetchNotifications()
    // Poll every 30s for passive background refresh
    intervalRef.current = setInterval(fetchNotifications, 30000)

    // Expose global refetch so any page can call window.__refetchNotifications?.()
    // after PM approve / assign / submit-review / final-approval
    window.__refetchNotifications = fetchNotifications

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
      delete window.__refetchNotifications
    }
  }, [fetchNotifications])

  // FIX: markRead is called only when user CLICKS a notification — not on dropdown open
  const markRead = async (id: number) => {
    try {
      const { fetchApi } = await import('@/lib/api')
      await fetchApi(`/rfps/notifications/${id}/read`, { method: 'POST' })
      // Update local state: mark as read but do NOT remove from list
      setNotifications(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n))
      // Recompute badge count from updated list
      setUnreadCount(prev => Math.max(0, prev - 1))
    } catch (e) {}
  }

  const clearAll = async () => {
    try {
      const { fetchApi } = await import('@/lib/api')
      await fetchApi('/rfps/notifications/clear-all', { method: 'POST' })
      // Mark all as read locally — do NOT remove from list
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })))
      setUnreadCount(0)
    } catch (e) {}
  }

  if (!user) return <header className="h-16 border-b border-zinc-200 bg-white" />

  const handleLogout = () => {
    localStorage.removeItem('rfp_user')
    router.push('/login')
  }

  const dashboardPath = user.role === 'pm' ? '/dashboard/ceo' : '/dashboard/architect'

  return (
    <header className="h-14 border-b border-zinc-200/60 bg-white/80 backdrop-blur-md px-5 flex items-center justify-between sticky top-0 z-40 w-full">
      <div className="flex items-center gap-4">
        {showSidebarToggle && (
          <button
            onClick={onSidebarToggle}
            className="p-1.5 rounded-lg hover:bg-zinc-100 text-zinc-500 hover:text-zinc-900 transition-all active:scale-95"
            title="Show Sidebar"
          >
            <PanelLeftOpen className="w-4.5 h-4.5" />
          </button>
        )}
        <div className="flex items-center gap-2.5">
          <span className="text-zinc-900 font-bold text-[13px] hidden lg:block tracking-tight">RFP Automation Platform</span>
          <span className="text-[10px] px-1.5 py-0.5 bg-zinc-100 rounded font-bold text-zinc-500 border border-zinc-200/50">v1.2</span>
        </div>
      </div>

      <div className="flex-1 max-w-lg mx-6 lg:mx-10">
        <div className="relative group">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-400 group-focus-within:text-zinc-900 transition-colors" />
          <Input
            placeholder="Search RFPs, clients, or requirements..."
            className="w-full pl-9 bg-zinc-50/50 border-zinc-200 focus-visible:ring-1 focus-visible:ring-zinc-400 h-9 text-xs font-medium placeholder:text-zinc-400/80 transition-all"
            defaultValue={typeof window !== 'undefined' ? new URLSearchParams(window.location.search).get('q') || '' : ''}
            onChange={(e) => {
              const term = e.target.value
              const url = new URL(window.location.href)
              if (term) { url.searchParams.set('q', term) } else { url.searchParams.delete('q') }
              router.replace(url.pathname + url.search)
            }}
          />
        </div>
      </div>

      <div className="flex items-center gap-5">
        {/* FIX: onOpenChange no longer clears the badge — badge is driven by unreadCount state only */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="text-zinc-400 hover:text-zinc-900 relative outline-none transition-colors p-1.5 rounded-lg hover:bg-zinc-50 active:scale-95">
              <Bell className="w-4.5 h-4.5" />
              {/* FIX: Show numeric badge when >0 unread, not just a dot */}
              {unreadCount > 0 && (
                <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 bg-indigo-500 text-white rounded-full text-[9px] font-black flex items-center justify-center border border-white leading-none">
                  {unreadCount > 9 ? '9+' : unreadCount}
                </span>
              )}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-80 bg-white border border-zinc-200 shadow-xl rounded-xl p-0 overflow-hidden mt-2">
            <div className="p-4 border-b border-zinc-100 flex justify-between items-center bg-zinc-50/30">
              <div className="flex items-center gap-2">
                <p className="text-[11px] font-bold text-zinc-900 uppercase tracking-widest">Notifications</p>
                {unreadCount > 0 && (
                  <span className="text-[9px] font-black bg-indigo-100 text-indigo-600 px-1.5 py-0.5 rounded-full">
                    {unreadCount} new
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3">
                {unreadCount > 0 && (
                  <button
                    onClick={(e) => { e.stopPropagation(); clearAll() }}
                    className="text-[9px] font-black uppercase text-indigo-600 hover:text-indigo-700 transition-colors"
                  >
                    Mark all read
                  </button>
                )}
                <span className="text-[9px] font-bold uppercase text-zinc-400 tracking-tighter">{notifications.length} recent</span>
              </div>
            </div>
            <div className="max-h-[400px] overflow-y-auto divide-y divide-zinc-50">
              {notifications.length > 0 ? (
                notifications.map((n) => (
                  <div
                    key={n.id}
                    // FIX: markRead only called on explicit click — not on dropdown open
                    onClick={() => { if (!n.is_read) markRead(n.id) }}
                    className={cn(
                      "p-3.5 cursor-pointer hover:bg-zinc-50/80 transition-colors relative",
                      // FIX: unread items have visual distinction — blue left border + tinted background
                      !n.is_read
                        ? "bg-indigo-50/30 border-l-2 border-l-indigo-500"
                        : "opacity-70"
                    )}
                  >
                    {/* Type badge */}
                    {n.type && (
                      <span className={cn(
                        "text-[8px] font-black uppercase tracking-wider px-1.5 py-0.5 rounded mr-1.5",
                        n.type === 'success' ? 'bg-emerald-100 text-emerald-700' :
                        n.type === 'error'   ? 'bg-red-100 text-red-700' :
                        n.type === 'warning' ? 'bg-amber-100 text-amber-700' :
                                               'bg-blue-100 text-blue-700'
                      )}>
                        {n.type}
                      </span>
                    )}
                    <p className={cn(
                      "text-[13px] leading-snug mt-1",
                      !n.is_read ? "text-zinc-900 font-semibold" : "text-zinc-500 font-medium"
                    )}>
                      {n.message}
                    </p>
                    <p className="text-[9px] text-zinc-400 mt-1.5 font-bold uppercase tracking-widest">
                      {formatNotificationTime(n.created_at)}
                    </p>
                  </div>
                ))
              ) : (
                <div className="p-10 flex flex-col items-center justify-center text-center space-y-3">
                  <div className="w-10 h-10 rounded-full bg-zinc-50 flex items-center justify-center">
                    <Bell className="w-5 h-5 text-zinc-300" />
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs font-bold text-zinc-900">All caught up!</p>
                    <p className="text-[10px] text-zinc-400 font-medium">No notifications yet.</p>
                  </div>
                </div>
              )}
            </div>
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger className="flex items-center gap-2 outline-none group">
            <div className="flex flex-col items-end mr-1 hidden sm:flex">
              <span className="text-[11px] font-bold text-zinc-900 leading-tight">{user.name}</span>
              <span className="text-[9px] text-zinc-400 font-bold uppercase tracking-widest leading-tight">{user.role}</span>
            </div>
            <Avatar className="w-8 h-8 rounded-full border border-zinc-200 group-hover:border-zinc-400 transition-colors">
              <AvatarFallback className="bg-white text-zinc-900 font-bold text-[10px] uppercase border border-zinc-200">{user.initials}</AvatarFallback>
            </Avatar>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56 bg-white border border-zinc-200 shadow-xl rounded-xl p-1.5 mt-2">
            <DropdownMenuLabel className="px-3 py-2.5">
              <div className="flex flex-col space-y-0.5">
                <p className="text-xs font-bold text-zinc-900 truncate">{user.name}</p>
                <p className="text-[10px] text-zinc-400 font-medium truncate">{user.email}</p>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator className="bg-zinc-100 mx-1" />
            <DropdownMenuItem
              onClick={() => router.push(`${dashboardPath}/profile`)}
              className="text-xs font-bold cursor-pointer py-2 px-3 hover:bg-zinc-50 focus:bg-zinc-50 rounded-lg flex items-center gap-2.5 text-zinc-600 hover:text-zinc-900"
            >
              <UserIcon className="w-3.5 h-3.5" />
              Profile
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => router.push(`${dashboardPath}/settings`)}
              className="text-xs font-bold cursor-pointer py-2 px-3 hover:bg-zinc-50 focus:bg-zinc-50 rounded-lg flex items-center gap-2.5 text-zinc-600 hover:text-zinc-900"
            >
              <SettingsIcon className="w-3.5 h-3.5" />
              Settings
            </DropdownMenuItem>
            <DropdownMenuSeparator className="bg-zinc-100 mx-1" />
            <DropdownMenuItem onClick={handleLogout} className="text-xs font-bold text-red-600 cursor-pointer py-2 px-3 hover:bg-red-50 focus:bg-red-50 focus:text-red-600 rounded-lg flex items-center gap-2.5">
              <LogOut className="w-3.5 h-3.5" />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
