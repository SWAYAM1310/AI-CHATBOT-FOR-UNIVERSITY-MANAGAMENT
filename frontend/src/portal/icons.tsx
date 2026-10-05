// The portal's navigation icons: plain 24px strokes that inherit the text colour.
import type { ReactNode } from 'react'

function Svg({ children, size = 20 }: { children: ReactNode; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  )
}

export const HomeIcon = () => (
  <Svg>
    <path d="M4 11.5 12 4l8 7.5" />
    <path d="M6 10v9h12v-9" />
    <path d="M10 19v-5h4v5" />
  </Svg>
)

export const ResultsIcon = () => (
  <Svg>
    <rect x="5" y="3.5" width="14" height="17" rx="2" />
    <path d="M9 16.5v-3M12 16.5v-7M15 16.5v-5" />
  </Svg>
)

export const BookIcon = () => (
  <Svg>
    <path d="M5 4.5h10a3 3 0 0 1 3 3V20H8a3 3 0 0 1-3-3V4.5Z" />
    <path d="M5 17a3 3 0 0 1 3-3h10" />
  </Svg>
)

export const CalendarIcon = () => (
  <Svg>
    <rect x="4" y="5.5" width="16" height="14.5" rx="2" />
    <path d="M4 10h16M8.5 3.5v4M15.5 3.5v4" />
    <path d="M8 14h2M14 14h2M8 17h2" />
  </Svg>
)

export const MegaphoneIcon = () => (
  <Svg>
    <path d="M4 10v4h3l8 4V6L7 10H4Z" />
    <path d="M18.5 9.5a4 4 0 0 1 0 5" />
  </Svg>
)

export const WalletIcon = () => (
  <Svg>
    <path d="M4 7.5A2.5 2.5 0 0 1 6.5 5H18v3" />
    <path d="M4 7.5V17a2 2 0 0 0 2 2h12a1 1 0 0 0 1-1v-9a1 1 0 0 0-1-1H6.5A2.5 2.5 0 0 1 4 7.5Z" />
    <circle cx="15.5" cy="13.5" r="1" />
  </Svg>
)

export const ChatIcon = () => (
  <Svg>
    <path d="M5 5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-7l-4.5 3.5V16H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z" />
  </Svg>
)

export const UserIcon = () => (
  <Svg>
    <circle cx="12" cy="8.5" r="3.5" />
    <path d="M5 19.5c.8-3.3 3.6-5 7-5s6.2 1.7 7 5" />
  </Svg>
)

export const MenuIcon = () => (
  <Svg>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </Svg>
)

export const SignOutIcon = () => (
  <Svg size={18}>
    <path d="M14 5H7a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h7" />
    <path d="M10 12h10m-3-3.5 3.5 3.5-3.5 3.5" />
  </Svg>
)
