import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ingest, query } from './api'
import type { HistoryTurn, QueryResult, Route, Source } from './types'

const ROUTE_LABELS: Record<Route, string> = {
  query: 'Data lookup',
  semantic: 'Text search',
  both: 'Data lookup + Text search',
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  route?: Route
  queries?: QueryResult[] | null
  sources?: Source[] | null
  queryError?: string | null
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function handleSend() {
    const q = input.trim()
    if (!q || loading) return
    setInput('')
    const history: HistoryTurn[] = messages.map((m) => ({ role: m.role, content: m.content }))
    setMessages((m) => [...m, { role: 'user', content: q }])
    setLoading(true)
    try {
      const res = await query(q, history)
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: res.answer,
          route: res.route,
          queries: res.queries,
          sources: res.sources,
          queryError: res.query_error,
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
        <div className="brand">
          <span className="brand-mark">M</span>
          <h1>MyAgent</h1>
        </div>
        <button className="ingest-btn" onClick={handleIngest}>
          Rebuild search index
        </button>
      </header>
      {status && <p className="status">{status}</p>}

      <div className="messages">
        {messages.length === 0 && (
          <div className="empty">
            <p className="empty-title">Ask anything about trainers, schedules, and leave</p>
            <p>
              Ask direct questions (“how many leave requests are pending?”)
              or open-ended ones (“what are trainers reporting in tickets?”).
              Run “Rebuild search index” once so free-text questions can be
              searched too.
            </p>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className={`avatar avatar-${m.role}`}>{m.role === 'user' ? 'U' : 'M'}</div>
            <div className="msg-body">
              <div className="bubble">
                {m.role === 'assistant' ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                ) : (
                  m.content
                )}
              </div>
              {m.route && <span className={`route route-${m.route}`}>{ROUTE_LABELS[m.route]}</span>}
              {m.queryError && (
                <div className="query-error">⚠ Something went wrong looking up that data. {m.queryError}</div>
              )}

              {m.queries?.map((q, j) => (
                <details className="detail" key={j}>
                  <summary>
                    Show the {q.rows.length} record(s) used from “{q.collection}”
                    {m.queries!.length > 1 && ` (${j + 1}/${m.queries!.length})`}
                  </summary>
                  <p className="detail-label">Records</p>
                  <pre>{JSON.stringify(q.rows, null, 2)}</pre>
                  <p className="detail-label">How they were filtered (technical)</p>
                  <pre>{JSON.stringify(q.pipeline, null, 2)}</pre>
                </details>
              ))}
              {m.sources && m.sources.length > 0 && (
                <details className="detail">
                  <summary>Show the {m.sources.length} reference(s) used</summary>
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
          </div>
        ))}
        {loading && (
          <div className="msg assistant">
            <div className="avatar avatar-assistant">M</div>
            <div className="msg-body">
              <div className="bubble typing">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="composer">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder="Ask a question…"
          disabled={loading}
        />
        <button onClick={handleSend} disabled={loading || !input.trim()}>
          Send
        </button>
      </div>
    </div>
  )
}
