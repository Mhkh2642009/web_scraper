import type { ScrapeRequest, ScrapeResponse } from '../types'

const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export async function scrape(payload: ScrapeRequest): Promise<ScrapeResponse> {
  const response = await fetch(`${apiBase}/api/scrape`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  const body = (await response.json()) as ScrapeResponse
  if (!response.ok && !('error' in body)) {
    return { success: false, code: 'REQUEST_FAILED', error: 'The request could not be completed.', trace: [] }
  }
  return body
}

