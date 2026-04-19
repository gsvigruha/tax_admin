import { useState } from 'react'
import FolderPicker from './components/FolderPicker'
import DocumentList from './components/DocumentList'
import TaxSummary from './components/TaxSummary'
import type { ScannedFile, TaxResult } from './types'

const API = 'http://localhost:8000'

interface Progress {
  current: number
  total: number
  fileName: string
  phase: 'reading' | 'analyzing'
}

export default function App() {
  const [scannedPath, setScannedPath] = useState('')
  const [files, setFiles] = useState<ScannedFile[]>([])
  const [result, setResult] = useState<TaxResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<{ msg: string; ok: boolean } | null>(null)
  const [progress, setProgress] = useState<Progress | null>(null)

  const post = async (endpoint: string, body: object) => {
    const res = await fetch(`${API}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail ?? 'Request failed')
    return data
  }

  const handleScan = async (path: string) => {
    setLoading(true)
    setStatus(null)
    try {
      const data = await post('/api/scan', { folder_path: path })
      setFiles(data.files ?? [])
      setScannedPath(path)
      setStatus({ msg: `Found ${data.total} supported file(s). Click "Analyze with AI" to extract tax data.`, ok: true })
    } catch (e: unknown) {
      setStatus({ msg: e instanceof Error ? e.message : String(e), ok: false })
    } finally {
      setLoading(false)
    }
  }

  const handleAnalyze = async (path: string) => {
    setLoading(true)
    setProgress(null)
    setStatus({ msg: 'Starting analysis…', ok: true })

    try {
      const res = await fetch(`${API}/api/analyze-stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_path: path }),
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail ?? 'Request failed')
      }

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const event = JSON.parse(line.slice(6))

          if (event.type === 'file') {
            setProgress({ current: event.current, total: event.total, fileName: event.name, phase: 'reading' })
            setStatus({ msg: `Reading file ${event.current} of ${event.total}…`, ok: true })
          } else if (event.type === 'analyzing') {
            setProgress({ current: event.batch ?? 1, total: event.total_batches ?? 1, fileName: '', phase: 'analyzing' })
            setStatus({ msg: event.message, ok: true })
          } else if (event.type === 'done') {
            setResult(event.result)
            setProgress(null)
            setStatus({ msg: 'Analysis complete. Results saved to tax_results.json.', ok: true })
          } else if (event.type === 'error') {
            throw new Error(event.message)
          }
        }
      }
    } catch (e: unknown) {
      setStatus({ msg: e instanceof Error ? e.message : String(e), ok: false })
      setProgress(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: 920, margin: '0 auto', padding: '2rem 1.5rem', fontFamily: 'system-ui, -apple-system, sans-serif', color: '#111' }}>
      <h1 style={{ fontSize: '1.6rem', fontWeight: 800, marginBottom: 4 }}>AI Tax Assistant</h1>
      <p style={{ color: '#6b7280', marginTop: 0, marginBottom: '1.5rem' }}>
        Point to a folder of tax documents — W2s, 1099s, bills, receipts — and let Claude extract income &amp; deductions.
      </p>

      <FolderPicker
        onScan={handleScan}
        onAnalyze={handleAnalyze}
        loading={loading}
        scannedPath={scannedPath}
      />

      {status && (
        <div style={{
          padding: '0.75rem 1rem',
          background: status.ok ? '#f0fdf4' : '#fef2f2',
          border: `1px solid ${status.ok ? '#bbf7d0' : '#fecaca'}`,
          borderRadius: 8, marginBottom: progress ? '0.5rem' : '1.25rem', fontSize: 14,
          color: status.ok ? '#166534' : '#991b1b',
        }}>
          {loading ? '⏳ ' : status.ok ? '✓ ' : '✗ '}{status.msg}
        </div>
      )}

      {progress && (
        <div style={{ marginBottom: '1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: '#6b7280', marginBottom: 4 }}>
            <span>
              {progress.phase === 'reading'
                ? `Reading: ${progress.fileName}`
                : 'Sending to Claude for analysis…'}
            </span>
            {progress.phase === 'reading' && (
              <span>{progress.current} / {progress.total}</span>
            )}
          </div>
          <div style={{ height: 6, background: '#e5e7eb', borderRadius: 999, overflow: 'hidden' }}>
            <div style={{
              height: '100%',
              width: `${(progress.current / Math.max(progress.total, 1)) * 100}%`,
              background: progress.phase === 'analyzing' ? '#f59e0b' : '#10b981',
              borderRadius: 999,
              transition: 'width 0.3s ease',
            }} />
          </div>
        </div>
      )}

      <DocumentList files={files} />
      {result && <TaxSummary result={result} />}
    </div>
  )
}
