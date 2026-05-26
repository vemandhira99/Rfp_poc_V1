'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { 
  Zap, 
  Shield, 
  Users, 
  Briefcase, 
  UserCircle2,
  ChevronRight
} from 'lucide-react'
import { cn } from '@/lib/utils'

export default function LoginPage() {
  const router = useRouter()
  const [role, setRole] = useState<'pm' | 'architect'>('pm')

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()

    const emailInput = (document.getElementById('email') as HTMLInputElement)?.value
    const passwordInput = (document.getElementById('password') as HTMLInputElement)?.value
    
    const emailToUse = emailInput || (role === 'architect' ? 'veman@company.com' : 'yash@company.com')
    const password = passwordInput || 'pm123'; // Default to pm123 for convenience if empty

    try {
      const response = await fetch(process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000' + '/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          email: emailToUse,
          password: password
        })
      });
      
      if (!response.ok) {
        throw new Error('Login failed');
      }
      
      const data = await response.json();
      
      // Save token and user data
      localStorage.setItem('rfp_token', data.access_token);
      localStorage.setItem('rfp_user', JSON.stringify({
        id: data.user_id,
        name: data.name,
        role: role,
        email: emailToUse
      }));
      
      router.push(role === 'architect' ? '/dashboard/architect' : '/dashboard/ceo')
    } catch(err) {
      alert('Login failed. Ensure backend is running.');
    }
  }

  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-white overflow-hidden">
      {/* Left Section - Project Info (Black) */}
      <div className="w-full md:w-[45%] bg-zinc-950 p-8 lg:p-12 flex flex-col justify-between text-white relative overflow-hidden">
        {/* Abstract background element */}
        <div className="absolute top-0 right-0 -mr-20 -mt-20 w-80 h-80 bg-blue-600/10 rounded-full blur-3xl"></div>
        <div className="absolute bottom-0 left-0 -ml-20 -mb-20 w-80 h-80 bg-purple-600/5 rounded-full blur-3xl"></div>
        
        <div className="relative z-10">
          <div className="flex items-center gap-2 mb-12">
            <div className="w-8 h-8 bg-white rounded-lg flex items-center justify-center">
              <span className="text-black font-black text-lg italic">R</span>
            </div>
            <span className="text-lg font-bold tracking-tight">RFP Automation</span>
          </div>

          <div className="space-y-6 max-w-sm">
            <h1 className="text-4xl font-bold leading-[1.1] tracking-tight">
              The Future of <br />
              <span className="text-zinc-500">RFP Responses.</span>
            </h1>
            <p className="text-base text-zinc-400 font-medium leading-relaxed">
              Accelerate your sales cycle with our AI-powered RFP automation platform. 
              Streamline compliance and collaboration.
            </p>

            <div className="space-y-4 pt-2">
              {[
                { icon: Zap, text: '60% faster response times with AI drafting' },
                { icon: Shield, text: 'Real-time compliance & risk assessment' },
                { icon: Users, text: 'Seamless global team collaboration' }
              ].map((item, i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className="p-1 rounded bg-zinc-800/50 border border-zinc-800">
                    <item.icon className="w-3.5 h-3.5 text-blue-400" />
                  </div>
                  <p className="text-sm text-zinc-300 font-medium">{item.text}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="relative z-10 pt-8">
          <div className="flex items-center gap-3 p-3 rounded-xl bg-zinc-900/40 border border-zinc-800/50 inline-flex">
            <div className="flex -space-x-1.5">
              {[1, 2, 3].map((i) => (
                <div key={i} className="w-6 h-6 rounded-full border-2 border-zinc-950 bg-zinc-800 flex items-center justify-center text-[8px] font-bold text-zinc-500">
                  U{i}
                </div>
              ))}
            </div>
            <p className="text-[11px] text-zinc-500 font-bold uppercase tracking-wider">Trusted by 500+ enterprises</p>
          </div>
        </div>
      </div>

      {/* Right Section - Login Form (White) */}
      <div className="w-full md:w-[55%] flex items-center justify-center p-8 bg-zinc-50/30">
        <div className="w-full max-w-[380px] space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
          <div className="space-y-6">
            {/* Role Switcher */}
            <div className="inline-flex p-1 bg-zinc-100/80 border border-zinc-200/50 rounded-xl w-full">
              <button 
                onClick={() => setRole('pm')}
                className={cn(
                  "flex-1 flex items-center justify-center gap-2 py-1.5 text-xs font-bold rounded-lg transition-all",
                  role === 'pm' ? "bg-white text-zinc-900 shadow-sm border border-zinc-200/50" : "text-zinc-500 hover:text-zinc-700"
                )}
              >
                <Briefcase className="w-3.5 h-3.5" />
                PM
              </button>
              <button 
                onClick={() => setRole('architect')}
                className={cn(
                  "flex-1 flex items-center justify-center gap-2 py-1.5 text-xs font-bold rounded-lg transition-all",
                  role === 'architect' ? "bg-white text-zinc-900 shadow-sm border border-zinc-200/50" : "text-zinc-500 hover:text-zinc-700"
                )}
              >
                <UserCircle2 className="w-3.5 h-3.5" />
                Architect
              </button>
            </div>

            <div className="space-y-1.5 text-center">
              <h2 className="text-2xl font-bold tracking-tight text-zinc-900">
                Welcome back
              </h2>
              <p className="text-zinc-500 font-medium text-sm">
                Sign in to your {role === 'pm' ? 'Manager' : 'Architect'} account
              </p>
            </div>
          </div>

          <form onSubmit={handleLogin} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="email" className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 ml-1">Email Address</Label>
              <Input 
                id="email" 
                type="email" 
                placeholder={role === 'pm' ? 'yash@company.com' : 'veman@company.com'} 
                required 
                className="input-premium h-11 px-4 text-sm font-medium" 
              />
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-center px-1">
                <Label htmlFor="password" className="text-[10px] font-bold uppercase tracking-widest text-zinc-400">Password</Label>
                <a href="#" className="text-[10px] font-bold text-zinc-400 hover:text-zinc-900 transition-colors uppercase tracking-widest">Forgot?</a>
              </div>
              <Input 
                id="password" 
                type="password" 
                placeholder="••••••••" 
                required 
                className="input-premium h-11 px-4 text-sm font-medium" 
              />
            </div>
            
            <Button 
              type="submit" 
              className="w-full h-11 bg-zinc-900 hover:bg-zinc-800 text-white font-bold text-sm rounded-xl transition-all shadow-sm group"
            >
              Sign in
              <ChevronRight className="w-4 h-4 ml-1.5 group-hover:translate-x-0.5 transition-transform" />
            </Button>
          </form>

          <div className="pt-6 border-t border-zinc-100 text-center">
            <p className="text-xs text-zinc-400 font-medium">
              New to the platform? <a href="#" className="text-zinc-900 font-bold hover:underline underline-offset-4 transition-all">Request access</a>
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
