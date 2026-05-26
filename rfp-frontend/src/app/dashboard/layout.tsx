'use client'

import { useState } from 'react'
import { Header } from '@/components/layout/Header'
import { Sidebar } from '@/components/layout/Sidebar'
import { cn } from '@/lib/utils'

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const [isSidebarVisible, setIsSidebarVisible] = useState(true)

  return (
    <div className="flex h-screen overflow-hidden bg-white text-zinc-900 antialiased">
      <aside
        className={cn(
          "h-screen border-r border-zinc-200/60 bg-white transition-all duration-300 ease-in-out z-50 flex-shrink-0 relative overflow-hidden",
          isSidebarVisible ? "w-56 opacity-100" : "w-0 opacity-0 border-none"
        )}
      >
        <div className="w-56 h-full">
          <Sidebar onToggle={() => setIsSidebarVisible(false)} />
        </div>
      </aside>

      <div className="flex-1 flex flex-col h-screen overflow-hidden relative">
        <Header
          showSidebarToggle={!isSidebarVisible}
          onSidebarToggle={() => setIsSidebarVisible(true)}
        />
        <main className="flex-1 overflow-y-auto bg-zinc-50/20 px-4 md:px-8 py-6">
          <div className="max-w-[1300px] mx-auto">
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}
