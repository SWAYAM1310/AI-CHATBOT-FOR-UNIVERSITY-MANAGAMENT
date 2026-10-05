import { useEffect, type ReactNode } from 'react'

/** The title block every portal page opens with; also names the browser tab. */
export function PageHeader({ title, lede, actions }: { title: string; lede?: ReactNode; actions?: ReactNode }) {
  useEffect(() => {
    const previous = document.title
    document.title = `${title} - UniAssist`
    return () => {
      document.title = previous
    }
  }, [title])

  return (
    <header className="page-header">
      <div>
        <h1 className="page-title">{title}</h1>
        {lede && <p className="page-lede">{lede}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  )
}
