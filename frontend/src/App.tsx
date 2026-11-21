import { CommandCenter } from './components/command/CommandCenter'
import { AdminDashboard } from './components/dashboard/AdminDashboard'
import { TopBar } from './components/TopBar'
import { useSimulation } from './hooks/useSimulation'
import { useHashRoute } from './lib/useHashRoute'

export default function App() {
  const [route, go] = useHashRoute()
  const sim = useSimulation()
  return (
    <div className="app">
      <TopBar route={route} go={go} online={sim.online} sim={sim.sim} />
      {/* The command center stays mounted (its 3-D view pauses) so switching tabs keeps the camera. */}
      <CommandCenter sim={sim} active={route === 'command'} onOpenDashboard={() => go('dashboard')} />
      {route === 'dashboard' && <AdminDashboard sim={sim} onOpenCommand={() => go('command')} />}
    </div>
  )
}
