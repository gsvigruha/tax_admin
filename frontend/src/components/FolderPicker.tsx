import { useState } from 'react'

const API = 'http://localhost:8000'

interface Props {
  onScan: (path: string) => void
  onAnalyze: (path: string) => void
  loading: boolean
  scannedPath: string
}

export default function FolderPicker({ onScan, onAnalyze, loading, scannedPath }: Props) {
  const [path, setPath] = useState(scannedPath)
  const [picking, setPicking] = useState(false)

  const handleBrowse = async () => {
    setPicking(true)
    try {
      const res = await fetch(`${API}/api/pick-folder`)
      if (!res.ok) return // user cancelled
      const { path: picked } = await res.json()
      setPath(picked)
      onScan(picked)
    } finally {
      setPicking(false)
    }
  }

  const disabled = loading || !path.trim()

  return (
    <div style={{ background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 12, padding: '1.5rem', marginBottom: '1.5rem' }}>
      <label style={{ display: 'block', fontWeight: 600, fontSize: 15, marginBottom: '0.75rem' }}>
        Tax Documents Folder
      </label>

      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        {/* Browse button — opens native macOS folder picker */}
        <button
          onClick={handleBrowse}
          disabled={loading || picking}
          style={{
            display: 'flex', alignItems: 'center', gap: '0.4rem',
            padding: '0.55rem 1rem',
            background: 'white', border: '1.5px solid #d1d5db', borderRadius: 8,
            cursor: loading || picking ? 'not-allowed' : 'pointer',
            fontWeight: 600, fontSize: 14, color: '#374151', whiteSpace: 'nowrap',
          }}
        >
          📁 {picking ? 'Opening…' : 'Browse…'}
        </button>

        {/* Path display / manual override */}
        <input
          type="text"
          value={path}
          onChange={e => setPath(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !disabled && onScan(path.trim())}
          placeholder="or paste a path here"
          style={{
            flex: 1, minWidth: 200,
            padding: '0.55rem 0.75rem',
            border: '1px solid #d1d5db', borderRadius: 8,
            fontSize: 13, fontFamily: 'monospace', color: '#374151',
          }}
        />

        <button
          onClick={() => onAnalyze(path.trim())}
          disabled={disabled}
          style={{
            padding: '0.55rem 1.25rem',
            background: disabled ? '#e5e7eb' : '#10b981',
            color: disabled ? '#9ca3af' : 'white',
            border: 'none', borderRadius: 8,
            cursor: disabled ? 'not-allowed' : 'pointer',
            fontWeight: 700, fontSize: 14, whiteSpace: 'nowrap',
          }}
        >
          {loading ? '⏳ Analyzing…' : '✨ Analyze with AI'}
        </button>
      </div>

      <p style={{ fontSize: 12, color: '#9ca3af', marginTop: '0.6rem', marginBottom: 0 }}>
        Files are read directly from disk — nothing is copied or uploaded. Supported: PDF, PNG, JPG, TXT, CSV.
      </p>
    </div>
  )
}
