import { useEffect, useState } from 'react'

export type Route = 'command' | 'dashboard'

const read = (): Route => (window.location.hash.startsWith('#/dashboard') ? 'dashboard' : 'command')

/** Minimal hash router: #/ = command center, #/dashboard = admin dashboard. */
export function useHashRoute(): [Route, (r: Route) => void] {
  const [route, setRoute] = useState<Route>(read)
  useEffect(() => {
    const onChange = () => setRoute(read())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  const go = (r: Route) => {
    window.location.hash = r === 'dashboard' ? '#/dashboard' : '#/'
  }
  return [route, go]
}
