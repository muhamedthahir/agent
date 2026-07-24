export interface Source {
  id: string
  collection: string
  text: string
}

export interface GeneratedQuery {
  collection: string
  pipeline: unknown[]
}

export type Route = 'query' | 'semantic' | 'both'

export interface QueryResponse {
  answer: string
  route: Route
  query?: GeneratedQuery | null
  rows?: Record<string, unknown>[] | null
  sources?: Source[] | null
}

export interface IngestResponse {
  ingested: number
  by_collection: Record<string, number>
}
