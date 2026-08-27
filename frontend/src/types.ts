export interface Source {
  id: string
  collection: string
  text: string
}

export interface QueryResult {
  collection: string
  pipeline: unknown[]
  rows: Record<string, unknown>[]
}

export type Route = 'query' | 'semantic' | 'both'

export interface HistoryTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface QueryResponse {
  answer: string
  route: Route
  queries?: QueryResult[] | null
  sources?: Source[] | null
  query_error?: string | null
}

export interface IngestResponse {
  ingested: number
  by_collection: Record<string, number>
}
