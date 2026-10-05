import { useEffect, useState } from 'react'
import { api } from '../api'

function initials(name: string | undefined): string {
  const parts = (name ?? '').trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  const first = parts[0][0]
  const last = parts.length > 1 ? parts[parts.length - 1][0] : ''
  return (first + last).toUpperCase()
}

/**
 * A person's photo, or their initials. A photo is only served to a signed-in
 * request, which an <img src> cannot make, so it is fetched with the token and
 * shown from an object URL. `version` changes when the photo does.
 */
export function Avatar({
  userId,
  name,
  hasPhoto,
  version = 0,
  size = 36,
}: {
  userId: number | undefined
  name: string | undefined
  hasPhoto: boolean | undefined
  version?: number
  size?: number
}) {
  const [src, setSrc] = useState<string | null>(null)

  useEffect(() => {
    if (!hasPhoto || userId == null) return
    let url: string | null = null
    let cancelled = false
    api
      .photo(userId)
      .then((blob) => {
        if (cancelled) return
        url = URL.createObjectURL(blob)
        setSrc(url)
      })
      .catch(() => {
        if (!cancelled) setSrc(null) // a missing photo is just initials, not an error
      })
    return () => {
      cancelled = true
      if (url) URL.revokeObjectURL(url)
    }
  }, [userId, hasPhoto, version])

  const shown = hasPhoto && userId != null ? src : null // a removed photo drops back to initials at once
  return (
    <span className="avatar" style={{ width: size, height: size, fontSize: Math.round(size * 0.4) }}>
      {shown ? <img src={shown} alt="" /> : initials(name)}
    </span>
  )
}
