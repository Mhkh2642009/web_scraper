import { FormEvent, KeyboardEvent, useEffect, useMemo, useState, type ReactNode } from 'react'
import { scrape } from './services/api'
import type { ScrapeResponse, ScrapeSuccess, TraceEntry } from './types'

type FormState = { url: string; query: string; expectedSelector: string }

const initialForm: FormState = {
  url: '',
  query: '',
  expectedSelector: '',
}

const methodLabel: Record<ScrapeSuccess['method'], string> = {
  direct_selector: 'Direct selector',
  ai_recovery: 'AI recovery',
  ai_discovery: 'AI discovery',
}

function CodeTag({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <span className={`code-tag ${className}`}>{children}</span>
}

function Trace({ trace, loading }: { trace: TraceEntry[]; loading: boolean }) {
  const [visibleCount, setVisibleCount] = useState(trace.length)

  useEffect(() => {
    if (!trace.length) {
      setVisibleCount(0)
      return
    }
    setVisibleCount(1)
    const timers = trace.slice(1).map((_, index) => window.setTimeout(() => setVisibleCount(index + 2), (index + 1) * 90))
    return () => timers.forEach(window.clearTimeout)
  }, [trace])

  if (!loading && !trace.length) return null
  return (
    <section className="trace-shell" aria-live="polite">
      <CodeTag>&lt;trace&gt;</CodeTag>
      <div className="trace-lines">
        {loading && <p className="trace-line active">&gt; backend pipeline in progress<span className="cursor">_</span></p>}
        {trace.slice(0, visibleCount).map((entry, index) => (
          <p className={`trace-line ${entry.status !== 'done' ? 'muted' : ''}`} key={`${entry.stage}-${index}`}>
            &gt; {entry.message}
          </p>
        ))}
      </div>
      <CodeTag>&lt;/trace&gt;</CodeTag>
    </section>
  )
}

function Result({ result, onReset }: { result: ScrapeSuccess; onReset: () => void }) {
  const [copied, setCopied] = useState('')
  const isRecovery = result.method === 'ai_recovery'

  async function copy(label: string, value: string) {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(label)
      window.setTimeout(() => setCopied(''), 1600)
    } catch {
      setCopied('Copy unavailable')
    }
  }

  return (
    <section className="code-block result-block" aria-labelledby="result-title">
      <CodeTag>&lt;<span className="syntax-element">result</span> <span className="syntax-attribute">status</span>=<span className="syntax-string">"found"</span>&gt;</CodeTag>
      <div className="result-content">
        <div className="result-heading">
          <div>
            <p className="eyebrow">Found value</p>
            <h2 id="result-title">{result.value}</h2>
          </div>
          <span className="method-label">{methodLabel[result.method]}</span>
        </div>

        {isRecovery && result.expected_selector && (
          <div className="healing" aria-label="Selector recovery result">
            <p><span>expected</span><code className="broken">{result.expected_selector}</code><b>not found</b></p>
            <p className="heal-arrow">↓</p>
            <p><span>detected</span><code>{result.detected_selector}</code><b>{Math.round(result.confidence * 100)}% match</b></p>
          </div>
        )}

        <dl className="result-details">
          {result.expected_selector && <><dt>Expected</dt><dd><code>{result.expected_selector}</code></dd></>}
          <dt>Detected</dt><dd><code>{result.detected_selector}</code></dd>
          <dt>Confidence</dt><dd>{Math.round(result.confidence * 100)}%</dd>
          <dt>Explanation</dt><dd>{result.explanation}</dd>
        </dl>
        <div className="html-preview">
          <p>Matched HTML</p>
          <pre><code>{result.matched_html}</code></pre>
        </div>
        <div className="actions">
          <button type="button" onClick={() => copy('value', result.value)}>Copy value</button>
          <button type="button" onClick={() => copy('selector', result.detected_selector)}>Copy selector</button>
          <button type="button" className="quiet" onClick={onReset}>Try again</button>
          <span className="copy-state" aria-live="polite">{copied ? `${copied} copied` : ''}</span>
        </div>
      </div>
      <CodeTag>&lt;/<span className="syntax-element">result</span>&gt;</CodeTag>
    </section>
  )
}

function ErrorResult({ result }: { result: Extract<ScrapeResponse, { success: false }> }) {
  return (
    <section className="code-block error-block" aria-live="assertive">
      <CodeTag>&lt;<span className="syntax-element">error</span> <span className="syntax-attribute">code</span>=<span className="syntax-string">"{result.code}"</span>&gt;</CodeTag>
      <p>{result.error}</p>
      <CodeTag>&lt;/<span className="syntax-element">error</span>&gt;</CodeTag>
    </section>
  )
}

export default function App() {
  const [form, setForm] = useState(initialForm)
  const [result, setResult] = useState<ScrapeResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [clientError, setClientError] = useState('')
  const trace = useMemo(() => result?.trace ?? [], [result])

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setClientError('')
    setResult(null)
    if (!form.url.trim() || !form.query.trim()) {
      setClientError('Add a public URL and describe the element you want to find.')
      return
    }
    setLoading(true)
    try {
      const response = await scrape({
        url: form.url.trim(),
        query: form.query.trim(),
        expected_selector: form.expectedSelector.trim() || undefined,
      })
      setResult(response)
    } catch {
      setResult({ success: false, code: 'NETWORK_ERROR', error: 'Could not reach the Scrapted API.', trace: [] })
    } finally {
      setLoading(false)
    }
  }

  function handleTextareaKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault()
      event.currentTarget.form?.requestSubmit()
    }
  }

  return (
    <main className="app-shell">
      <div className="editor" aria-label="Scrapted scraping workspace">
        <header className="editor-tab"><span className="file-dot" aria-hidden="true" />index.html</header>
        <div className="editor-body">
          <div className="line-numbers" aria-hidden="true">{Array.from({ length: 24 }, (_, index) => <span key={index}>{index + 1}</span>)}</div>
          <div className="source">
            <p><span className="syntax-punctuation">&lt;!</span><span className="syntax-keyword">DOCTYPE</span> <span className="syntax-element">html</span><span className="syntax-punctuation">&gt;</span></p>
            <p><CodeTag>&lt;<span className="syntax-element">html</span> <span className="syntax-attribute">lang</span>=<span className="syntax-string">"en"</span>&gt;</CodeTag></p>
            <div className="indent-guide">
              <p><CodeTag>&lt;<span className="syntax-element">head</span>&gt;</CodeTag></p>
              <section className="brand-block">
                <h1>scrapted<span className="cursor">_</span></h1>
                <p>Tell us what you want. We&apos;ll find where the DOM hid it.</p>
              </section>
              <p><CodeTag>&lt;/<span className="syntax-element">head</span>&gt;</CodeTag></p>
            </div>
            <div className="indent-guide">
              <p><CodeTag>&lt;<span className="syntax-element">body</span>&gt;</CodeTag></p>
              <div className="indent-guide">
                <p><CodeTag>&lt;<span className="syntax-element">main</span> <span className="syntax-attribute">class</span>=<span className="syntax-string">"scrapted"</span>&gt;</CodeTag></p>
                <section className="code-block form-block">
                  <CodeTag>&lt;<span className="syntax-element">form</span> <span className="syntax-attribute">class</span>=<span className="syntax-string">"scrape"</span>&gt;</CodeTag>
                  <form onSubmit={submit} noValidate>
                    <label>
                      <span>Website URL</span>
                      <input type="url" value={form.url} onChange={(event) => update('url', event.target.value)} placeholder="https://example.com/products" disabled={loading} required />
                    </label>
                    <label>
                      <span>What do you want to find?</span>
                      <textarea value={form.query} onChange={(event) => update('query', event.target.value)} onKeyDown={handleTextareaKeyDown} placeholder="Find the price of the first product" disabled={loading} required rows={3} />
                      <small>Use Ctrl/Cmd + Enter to run from this field.</small>
                    </label>
                    <label>
                      <span>Expected ID / CSS selector <em>optional</em></span>
                      <input value={form.expectedSelector} onChange={(event) => update('expectedSelector', event.target.value)} placeholder="#product-price" disabled={loading} />
                    </label>
                    {clientError && <p className="inline-error">{clientError}</p>}
                    <button className="primary-action" type="submit" disabled={loading}>{loading ? 'Scraping…' : 'Scrape →'}</button>
                  </form>
                  <CodeTag>&lt;/<span className="syntax-element">form</span>&gt;</CodeTag>
                </section>
                <Trace trace={trace} loading={loading} />
                {result?.success && <Result result={result} onReset={() => setResult(null)} />}
                {result && !result.success && <ErrorResult result={result} />}
                <p><CodeTag>&lt;/<span className="syntax-element">main</span>&gt;</CodeTag></p>
              </div>
              <p><CodeTag>&lt;/<span className="syntax-element">body</span>&gt;</CodeTag></p>
            </div>
            <p><CodeTag>&lt;/<span className="syntax-element">html</span>&gt;</CodeTag></p>
          </div>
        </div>
      </div>
    </main>
  )
}
