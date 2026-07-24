import { useState } from 'react'
import { ingest, query } from './api'
import type { GeneratedQuery, Route, Source } from './types'

interface Message {
  role: 'user' | 'assistant'
  content: string
  route?: Route
  generatedQuery?: GeneratedQuery | null
  rows?: Record<string, unknown>[] | null
  sources?: Source[] | null
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')

  async function handleSend() {
    const q = input.trim()
    if (!q || loading) return
    setInput('')
    setMessages((m) => [...m, { role: 'user', content: q }])
    setLoading(true)
    try {
      const res = await query(q)
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: res.answer,
          route: res.route,
          generatedQuery: res.query,
          rows: res.rows,
          sources: res.sources,
        },
      ])
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: `Error: ${(e as Error).message}` },
      ])
    } finally {
      setLoading(false)
    }
  }

  async function handleIngest() {
    setStatus('Rebuilding search index…')
    try {
      const res = await ingest()
      const detail = Object.entries(res.by_collection)
        .map(([k, v]) => `${k}: ${v}`)
        .join(', ')
      setStatus(`Indexed ${res.ingested} document(s). [${detail}]`)
    } catch (e) {
      setStatus(`Index error: ${(e as Error).message}`)
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>MyAgent</h1>
        <button className="ingest-btn" onClick={handleIngest}>
          Rebuild search index
        </button>
      </header>
      {status && <p className="status">{status}</p>}

      <div className="messages">
        {messages.length === 0 && (
          <p className="empty">
            Ask about your TOMS data — operational questions (“how many leaves
            are pending?”) or free-text ones (“what are trainers reporting in
            tickets?”). Run “Rebuild search index” once to enable semantic
            search.
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="bubble">{m.content}</div>
            {m.route && <span className={`route route-${m.route}`}>{m.route}</span>}

            {m.generatedQuery && (
              <details className="detail">
                <summary>MongoDB query · {m.generatedQuery.collection}</summary>
                <pre>{JSON.stringify(m.generatedQuery.pipeline, null, 2)}</pre>
              </details>
            )}
            {m.rows && m.rows.length > 0 && (
              <details className="detail">
                <summary>{m.rows.length} row(s)</summary>
                <pre>{JSON.stringify(m.rows, null, 2)}</pre>
              </details>
            )}
            {m.sources && m.sources.length > 0 && (
              <details className="detail">
                <summary>{m.sources.length} source(s)</summary>
                {m.sources.map((s, j) => (
                  <div key={j} className="source">
                    <code>
                      {s.collection}:{s.id}
                    </code>
                    <pre>{s.text}</pre>
                  </div>
                ))}
              </details>
            )}
          </div>
        ))}
        {loading && (
          <div className="msg assistant">
            <div className="bubble">…</div>
          </div>
        )}
      </div>

      <div className="composer">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder="Ask a question…"
          disabled={loading}
        />
        <button onClick={handleSend} disabled={loading}>
          Send
        </button>
      </div>
    </div>
  )
}
