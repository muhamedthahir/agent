import type { IngestResponse, QueryResponse } from './types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

export async function query(question: string): Promise<QueryResponse> {
  const res = await fetch(`${API_URL}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  if (!res.ok) throw new Error(`Query failed (${res.status})`)
  return res.json() as Promise<QueryResponse>
}

export async function ingest(): Promise<IngestResponse> {
  const res = await fetch(`${API_URL}/ingest`, { method: 'POST' })
  if (!res.ok) throw new Error(`Ingest failed (${res.status})`)
  return res.json() as Promise<IngestResponse>
}
