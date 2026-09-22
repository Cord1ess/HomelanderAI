import type { ReactNode } from 'react'
import { useLocation } from 'react-router-dom'

/**
 * Each screen rises in as it opens. Keyed on the path, so moving between
 * screens replays it and staying on one does not. The animation is CSS
 * (`.page-enter` in index.css) and collapses under reduced motion.
 */
export function PageTransition({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  return (
    <div key={pathname} className="page-enter">
      {children}
    </div>
  )
}
