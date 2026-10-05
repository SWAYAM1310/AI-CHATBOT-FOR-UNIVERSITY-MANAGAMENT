import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './portal.css'
import './pages.css'
import './calendar.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
