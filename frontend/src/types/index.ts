export type TraceEntry = {
  stage: string
  status: string
  message: string
}

export type ScrapeSuccess = {
  success: true
  value: string
  expected_selector: string | null
  detected_selector: string
  matched_html: string
  confidence: number
  method: 'direct_selector' | 'ai_recovery' | 'ai_discovery'
  explanation: string
  trace: TraceEntry[]
}

export type ScrapeFailure = {
  success: false
  code: string
  error: string
  trace: TraceEntry[]
}

export type ScrapeResponse = ScrapeSuccess | ScrapeFailure

export type ScrapeRequest = {
  url: string
  query: string
  expected_selector?: string
}

