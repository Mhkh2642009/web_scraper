import type { ScrapeRequest, ScrapeResponse } from '../types'

// In development Vite proxies /api to the local FastAPI server. Set this only
// for a deployed frontend that needs to call a separate public API origin.
const apiBase = import.meta.env.VITE_API_BASE_URL || ''

const apiKeyHeader = (apiKey: string) => ({ 'X-Gemini-API-Key': apiKey })

export async function validateApiKey(apiKey: string): Promise<void> {
  const response = await fetch(`${apiBase}/api/ai/validate`, {
    method: 'POST',
    headers: apiKeyHeader(apiKey),
  })
  if (response.ok) return
  const body = await response.json().catch(() => null) as { error?: string } | null
  throw new Error(body?.error || 'The API key could not be verified. Try again.')
}

export async function scrape(payload: ScrapeRequest, apiKey: string): Promise<ScrapeResponse> {
  const response = await fetch(`${apiBase}/api/scrape`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...apiKeyHeader(apiKey) },
    body: JSON.stringify(payload),
  })

  const body = (await response.json()) as ScrapeResponse
  if (!response.ok && !('error' in body)) {
    return { success: false, code: 'REQUEST_FAILED', error: 'The request could not be completed.', trace: [] }
  }
  return body
}

export type StreamUpdate =
  | { type: 'submitted' | 'ai_waiting'; message: string }
  | { type: 'source_ready'; source_preview: string }
  | { type: 'compressed_dom'; compressed_dom: string }

export async function scrapeStream(payload: ScrapeRequest, apiKey: string, onUpdate: (update: StreamUpdate) => void): Promise<ScrapeResponse> {
  const response = await fetch(`${apiBase}/api/scrape/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...apiKeyHeader(apiKey) },
    body: JSON.stringify(payload),
  })
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => null) as ScrapeResponse | null
    return body && 'error' in body ? body : { success: false, code: 'REQUEST_FAILED', error: 'The request could not be completed.', trace: [] }
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let finalResult: ScrapeResponse | null = null
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      const event = block.match(/^event: (.+)$/m)?.[1]
      const data = block.match(/^data: (.+)$/m)?.[1]
      if (!event || !data) continue
      const parsed = JSON.parse(data) as StreamUpdate | ScrapeResponse
      if (event === 'result') finalResult = parsed as ScrapeResponse
      else onUpdate(parsed as StreamUpdate)
    }
    if (done) break
  }
  return finalResult ?? { success: false, code: 'REQUEST_FAILED', error: 'The request ended before Scrapted returned a result.', trace: [] }
}
