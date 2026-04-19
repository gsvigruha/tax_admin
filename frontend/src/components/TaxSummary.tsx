import type { TaxResult } from '../types'

const usd = (n: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n ?? 0)

const pill = (bg: string, text: string): React.CSSProperties => ({
  background: bg, color: text, borderRadius: 4, padding: '2px 7px', fontSize: 11, fontWeight: 600,
})

const th: React.CSSProperties = {
  padding: '0.5rem 0.75rem', textAlign: 'left', fontSize: 13, fontWeight: 600,
  borderBottom: '1px solid #e5e7eb', background: '#f9fafb',
}

const td: React.CSSProperties = {
  padding: '0.5rem 0.75rem', fontSize: 13, borderBottom: '1px solid #f3f4f6',
}

export default function TaxSummary({ result }: { result: TaxResult }) {
  return (
    <div>
      <h2 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '1rem' }}>Tax Analysis Results</h2>

      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
        {[
          { label: 'Total Income', value: result.total_income, color: '#10b981' },
          { label: 'Total Deductions', value: result.total_deductions, color: '#3b82f6' },
          { label: 'Est. Payments', value: result.total_estimated_payments, color: '#8b5cf6' },
          { label: 'Taxable Income (est.)', value: result.estimated_taxable_income, color: '#f59e0b' },
        ].map(c => (
          <div key={c.label} style={{ background: 'white', border: '1px solid #e5e7eb', borderRadius: 12, padding: '1rem', textAlign: 'center' }}>
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>{c.label}</div>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: c.color }}>{usd(c.value)}</div>
          </div>
        ))}
      </div>

      {/* Income table */}
      {result.income?.length > 0 && (
        <div style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#065f46', marginBottom: '0.5rem' }}>Income</h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead><tr>{['Description', 'Source', 'Type', 'Amount'].map(h => <th key={h} style={th}>{h}</th>)}</tr></thead>
              <tbody>
                {result.income.map((item, i) => (
                  <tr key={i}>
                    <td style={td}>{item.description}</td>
                    <td style={{ ...td, color: '#6b7280' }}>{item.source}</td>
                    <td style={td}><span style={pill('#d1fae5', '#065f46')}>{item.type}</span></td>
                    <td style={{ ...td, fontWeight: 600 }}>{usd(item.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Deductions table */}
      {result.deductions?.length > 0 && (
        <div style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#1e40af', marginBottom: '0.5rem' }}>Deductions</h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead><tr>{['Description', 'Category', 'Amount'].map(h => <th key={h} style={th}>{h}</th>)}</tr></thead>
              <tbody>
                {result.deductions.map((item, i) => (
                  <tr key={i}>
                    <td style={td}>{item.description}</td>
                    <td style={td}><span style={pill('#dbeafe', '#1e40af')}>{item.category}</span></td>
                    <td style={{ ...td, fontWeight: 600 }}>{usd(item.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Estimated payments table */}
      {result.estimated_payments?.length > 0 && (
        <div style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#5b21b6', marginBottom: '0.5rem' }}>Estimated Tax Payments</h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead><tr>{['Description', 'Date', 'Jurisdiction', 'Amount'].map(h => <th key={h} style={th}>{h}</th>)}</tr></thead>
              <tbody>
                {result.estimated_payments.map((item, i) => (
                  <tr key={i}>
                    <td style={td}>{item.description}</td>
                    <td style={{ ...td, color: '#6b7280' }}>{item.date}</td>
                    <td style={td}><span style={pill('#ede9fe', '#5b21b6')}>{item.jurisdiction}</span></td>
                    <td style={{ ...td, fontWeight: 600 }}>{usd(item.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Summary */}
      {result.summary && (
        <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 8, padding: '1rem', marginBottom: '1rem', fontSize: 14 }}>
          <strong>Summary:</strong> {result.summary}
        </div>
      )}

      {/* Notes */}
      {result.notes?.length > 0 && (
        <div style={{ background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, padding: '1rem', fontSize: 13 }}>
          <strong>Notes:</strong>
          <ul style={{ margin: '0.4rem 0 0 1.2rem', padding: 0 }}>
            {result.notes.map((n, i) => <li key={i}>{n}</li>)}
          </ul>
        </div>
      )}
    </div>
  )
}
