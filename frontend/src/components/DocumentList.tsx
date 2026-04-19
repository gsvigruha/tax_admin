import { useState } from 'react'
import type { ScannedFile } from '../types'

const TYPE_COLOR: Record<string, string> = {
  '.pdf': '#ef4444',
  '.png': '#8b5cf6',
  '.jpg': '#8b5cf6',
  '.jpeg': '#8b5cf6',
  '.txt': '#6b7280',
  '.csv': '#f59e0b',
}

function FileCard({ f }: { f: ScannedFile }) {
  const [tooltip, setTooltip] = useState<{ x: number; y: number } | null>(null)

  return (
    <div
      key={f.path}
      style={{ position: 'relative', background: 'white', border: '1px solid #e5e7eb', borderRadius: 8, padding: '0.6rem 0.8rem', display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 0 }}
      onMouseEnter={e => setTooltip({ x: e.clientX, y: e.clientY })}
      onMouseMove={e => setTooltip({ x: e.clientX, y: e.clientY })}
      onMouseLeave={() => setTooltip(null)}
    >
      <span style={{ background: TYPE_COLOR[f.type] ?? '#6b7280', color: 'white', borderRadius: 4, padding: '2px 6px', fontSize: 10, fontWeight: 700, textTransform: 'uppercase', flexShrink: 0 }}>
        {f.type.replace('.', '')}
      </span>
      <span style={{ fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>
        {f.name}
      </span>
      {tooltip && (
        <div style={{
          position: 'fixed',
          left: tooltip.x + 12,
          top: tooltip.y + 12,
          background: '#1f2937',
          color: 'white',
          fontSize: 12,
          padding: '5px 9px',
          borderRadius: 6,
          pointerEvents: 'none',
          zIndex: 9999,
          maxWidth: 400,
          wordBreak: 'break-all',
          boxShadow: '0 4px 12px rgba(0,0,0,0.25)',
        }}>
          {f.path}
        </div>
      )}
    </div>
  )
}

export default function DocumentList({ files }: { files: ScannedFile[] }) {
  if (!files.length) return null
  return (
    <div style={{ marginBottom: '1.5rem' }}>
      <h2 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '0.75rem' }}>
        Found {files.length} document{files.length !== 1 ? 's' : ''}
      </h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.5rem' }}>
        {files.map(f => <FileCard key={f.path} f={f} />)}
      </div>
    </div>
  )
}
