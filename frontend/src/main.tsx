import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
// Self-hosted fonts (Latin + Latin Extended, which includes ₹): no request to a third-party font server
import '@fontsource/inter/latin-400.css'
import '@fontsource/inter/latin-ext-400.css'
import '@fontsource/inter/latin-500.css'
import '@fontsource/inter/latin-ext-500.css'
import '@fontsource/inter/latin-600.css'
import '@fontsource/inter/latin-ext-600.css'
import '@fontsource/inter/latin-700.css'
import '@fontsource/inter/latin-ext-700.css'
import '@fontsource/inter/latin-800.css'
import '@fontsource/inter/latin-ext-800.css'
import '@fontsource/inter/latin-900.css'
import '@fontsource/inter/latin-ext-900.css'
import '@fontsource/jetbrains-mono/latin-400.css'
import App from './App'
import { AuthProvider } from './auth'
import { Toaster } from './lib/notify'
import { queryClient } from './queries'
import './index.css'

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <App />
        <Toaster />
      </AuthProvider>
    </QueryClientProvider>
  </React.StrictMode>,
)
