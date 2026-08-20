import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { scrapeStream, validateApiKey, type StreamUpdate } from './services/api'
import type { ScrapeResponse, ScrapeSuccess, TraceEntry } from './types'

type FormState = { url: string; query: string; expectedSelector: string }

const initialForm: FormState = {
  url: '',
  query: '',
  expectedSelector: '',
}

const apiKeySessionKey = 'scrapted_gemini_api_key'

function getSessionApiKey() {
  try {
    return window.sessionStorage.getItem(apiKeySessionKey) ?? ''
  } catch {
    return ''
  }
}

const methodLabel: Record<ScrapeSuccess['method'], string> = {
  direct_selector: 'Direct selector',
  ai_recovery: 'AI recovery',
  ai_discovery: 'AI discovery',
}

function CodeTag({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <span className={`code-tag ${className}`}>{children}</span>
}

function TypingText({ text, active }: { text: string; active: boolean }) {
  const [visibleText, setVisibleText] = useState(active ? '' : text)

  useEffect(() => {
    if (!active) {
      setVisibleText(text)
      return
    }
    setVisibleText('')
    let index = 0
    const timer = window.setInterval(() => {
      index += 1
      setVisibleText(text.slice(0, index))
      if (index >= text.length) window.clearInterval(timer)
    }, 24)
    return () => window.clearInterval(timer)
  }, [text, active])

  return (
    <span className="live-typing" aria-label={text}>
      <span aria-hidden="true">{visibleText}</span>
      {active && <i className="typing-beam" aria-hidden="true" />}
    </span>
  )
}

function highlightAttributes(value: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const attributePattern = /(\s+)([^\s=/>]+)(?:\s*(=)\s*("[^"]*"|'[^']*'|[^\s>]+))?/g
  let cursor = 0
  let match: RegExpExecArray | null

  while ((match = attributePattern.exec(value))) {
    if (match.index > cursor) nodes.push(value.slice(cursor, match.index))
    nodes.push(match[1])
    nodes.push(<span className="code-attribute" key={`${keyPrefix}-name-${match.index}`}>{match[2]}</span>)
    if (match[3]) nodes.push(<span className="code-operator" key={`${keyPrefix}-operator-${match.index}`}>=</span>)
    if (match[4]) nodes.push(<span className="code-string" key={`${keyPrefix}-value-${match.index}`}>{match[4]}</span>)
    cursor = attributePattern.lastIndex
  }
  if (cursor < value.length) nodes.push(value.slice(cursor))
  return nodes
}

function highlightHtml(line: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const markupPattern = /(<!--.*?-->|<![^>]*>|<\/?[A-Za-z][^>]*>)/g
  let cursor = 0
  let match: RegExpExecArray | null

  while ((match = markupPattern.exec(line))) {
    if (match.index > cursor) {
      nodes.push(<span className="code-text" key={`text-${cursor}`}>{line.slice(cursor, match.index)}</span>)
    }
    const token = match[0]
    if (token.startsWith('<!--')) {
      nodes.push(<span className="code-comment" key={`comment-${match.index}`}>{token}</span>)
    } else if (token.startsWith('<!')) {
      nodes.push(<span className="code-doctype" key={`doctype-${match.index}`}>{token}</span>)
    } else {
      const tag = token.match(/^(<\/?)([A-Za-z][\w:-]*)([\s\S]*?)(\/?>)$/)
      if (!tag) {
        nodes.push(token)
      } else {
        nodes.push(<span className="code-punctuation" key={`open-${match.index}`}>{tag[1]}</span>)
        nodes.push(<span className="code-element" key={`tag-${match.index}`}>{tag[2]}</span>)
        nodes.push(...highlightAttributes(tag[3], `attr-${match.index}`))
        nodes.push(<span className="code-punctuation" key={`close-${match.index}`}>{tag[4]}</span>)
      }
    }
    cursor = markupPattern.lastIndex
  }
  if (cursor < line.length) nodes.push(<span className="code-text" key={`text-${cursor}`}>{line.slice(cursor)}</span>)
  return nodes
}

function highlightCandidate(line: string): ReactNode[] {
  return line.split(/(\[[^\]]+\]|\b(?:css|text|in):|\b(?:id|class|href|title|name|src|value|content|aria-label)=|\|)/g).filter(Boolean).map((token, index) => {
    if (/^\[[^\]]+\]$/.test(token)) return <span className="code-index" key={index}>{token}</span>
    if (token === '|') return <span className="code-punctuation" key={index}>{token}</span>
    if (/^(?:(?:css|text|in):|(?:id|class|href|title|name|src|value|content|aria-label)=)$/.test(token)) return <span className="code-attribute" key={index}>{token}</span>
    return <span className="code-text" key={index}>{token}</span>
  })
}

type FormattedSourceLine = { content: string; indent: number }

function formatSource(source: string): FormattedSourceLine[] {
  const voidElements = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'param', 'source', 'track', 'wbr'])
  let depth = 0
  return source.split('\n').filter(Boolean).map((content) => {
    const trimmed = content.trim()
    const closingTag = trimmed.match(/^<\/([A-Za-z][\w:-]*)/)
    if (closingTag) depth = Math.max(0, depth - 1)
    const line = { content: trimmed, indent: Math.min(depth, 7) }
    const openingTag = trimmed.match(/^<([A-Za-z][\w:-]*)\b[^>]*>/)
    if (openingTag) {
      const tagName = openingTag[1].toLowerCase()
      const closesInline = new RegExp(`<\/${openingTag[1]}\s*>`, 'i').test(trimmed)
      if (!voidElements.has(tagName) && !trimmed.endsWith('/>') && !closesInline) depth += 1
    }
    return line
  })
}

function FormattedCandidate({ line }: { line: string }) {
  const segments = line.split(/\s+\|\s+/).filter(Boolean)
  return (
    <span className="code-content candidate-content">
      {segments.map((segment, index) => (
        <span className={`candidate-segment ${index === 0 ? 'candidate-primary' : ''}`} key={`${segment}-${index}`}>
          {index > 0 && <span className="candidate-branch" aria-hidden="true">↳</span>}
          {highlightCandidate(segment)}
        </span>
      ))}
    </span>
  )
}

function Trace({ trace, loading, progressMessage }: { trace: TraceEntry[]; loading: boolean; progressMessage: string }) {
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
        {loading && <p className="trace-line active">&gt; {progressMessage}<span className="cursor">_</span></p>}
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

type InspectionPhase = 'fetching' | 'source' | 'compressing' | 'ai' | 'done'

const agentSteps = [
  { phase: 'fetching', label: 'Open page' },
  { phase: 'source', label: 'Read markup' },
  { phase: 'compressing', label: 'Rewrite DOM' },
  { phase: 'ai', label: 'Match request' },
] as const

const agentNotes: Record<InspectionPhase, string[]> = {
  fetching: ['Opening a secure connection', 'Waiting for the page response', 'Preparing a clean workspace'],
  source: ['Reading the returned markup', 'Mapping visible text nodes', 'Marking scripts and metadata to skip'],
  compressing: ['Selecting useful content nodes', 'Removing low-signal markup', 'Rewriting nodes as compact records'],
  ai: ['Comparing candidates to your request', 'Testing the strongest semantic match', 'Preparing a selector for verification'],
  done: ['Review complete'],
}

function SourceInspector({ result, query, phase }: { result: Pick<ScrapeResponse, 'source_preview' | 'compressed_dom'>; query: string; phase: InspectionPhase }) {
  const [visibleSourceLines, setVisibleSourceLines] = useState(0)
  const [visibleCandidateLines, setVisibleCandidateLines] = useState(0)
  const [activityTick, setActivityTick] = useState(0)
  const [focusLine, setFocusLine] = useState(0)
  const sourcePreview = result.source_preview ?? ''
  const compressedDom = result.compressed_dom ?? ''
  const sourceLines = useMemo(() => formatSource(sourcePreview), [sourcePreview])
  const candidateLines = compressedDom.split('\n').filter(Boolean)
  const phaseIndex = agentSteps.findIndex((step) => step.phase === phase)
  const activeStepNumber = phase === 'done' ? agentSteps.length : Math.max(phaseIndex + 1, 1)
  const activeNote = agentNotes[phase][activityTick % agentNotes[phase].length]
  const phaseLabel = phase === 'fetching' ? 'opening page' : phase === 'source' ? 'reading markup' : phase === 'compressing' ? 'rewriting DOM' : phase === 'ai' ? 'matching request' : 'work complete'

  useEffect(() => {
    setActivityTick(0)
    if (phase === 'done') return
    const timer = window.setInterval(() => setActivityTick((current) => current + 1), 1900)
    return () => window.clearInterval(timer)
  }, [phase])

  useEffect(() => {
    if (!sourceLines.length) {
      setVisibleSourceLines(0)
      return
    }
    if (phase !== 'source') {
      setVisibleSourceLines(sourceLines.length)
      return
    }
    setVisibleSourceLines(0)
    const timer = window.setInterval(() => {
      setVisibleSourceLines((current) => Math.min(current + 1, sourceLines.length))
    }, 28)
    return () => window.clearInterval(timer)
  }, [phase, sourcePreview, sourceLines.length])

  useEffect(() => {
    if (!candidateLines.length) {
      setVisibleCandidateLines(0)
      return
    }
    if (phase === 'done') {
      setVisibleCandidateLines(candidateLines.length)
      return
    }
    if (phase !== 'compressing' && phase !== 'ai') {
      setVisibleCandidateLines(0)
      return
    }
    setVisibleCandidateLines(0)
    const timer = window.setInterval(() => {
      setVisibleCandidateLines((current) => Math.min(current + 1, candidateLines.length))
    }, 76)
    return () => window.clearInterval(timer)
  }, [phase, compressedDom, candidateLines.length])

  useEffect(() => {
    if (phase === 'done') return
    const lineCount = phase === 'compressing' || phase === 'ai' ? candidateLines.length : sourceLines.length
    if (!lineCount) return
    setFocusLine(0)
    const timer = window.setInterval(() => {
      setFocusLine((current) => (current + 1 + (current % 3 === 0 ? 1 : 0)) % lineCount)
    }, 340)
    return () => window.clearInterval(timer)
  }, [phase, sourceLines.length, candidateLines.length])

  return (
    <section id="agent-workbench" className={`inspector phase-${phase} ${phase !== 'done' ? 'is-inspecting' : ''}`} aria-label="Page source inspection">
      <div className="inspector-header">
        <div className="agent-identity">
          <span className="agent-mark" aria-hidden="true"><i />A</span>
          <div><span className="eyebrow">Scrapted workspace</span><strong><TypingText text={activeNote} active={phase !== 'done'} /></strong></div>
        </div>
        <div className={`agent-run-status ${phase !== 'done' ? 'active' : ''}`}>
          <span className="run-state"><i /><span><small>Run status</small><strong>{phaseLabel}</strong></span></span>
          <b>{String(activeStepNumber).padStart(2, '0')}<small>/04</small></b>
        </div>
      </div>
      <ol className="agent-steps" aria-label="Scraping progress">
        {agentSteps.map((step, index) => {
          const status = phase === 'done' || index < phaseIndex ? 'complete' : index === phaseIndex ? 'current' : 'upcoming'
          return (
            <li className={status} key={step.phase}>
              <span className="step-number">{status === 'complete' ? '✓' : String(index + 1).padStart(2, '0')}</span>
              <span className="step-copy"><strong>{step.label}</strong><small>{status === 'complete' ? 'complete' : status === 'current' ? 'in progress' : 'queued'}</small></span>
            </li>
          )
        })}
      </ol>
      <div className="agent-request"><span>Objective</span><i aria-hidden="true">→</i><p>{query || 'Waiting for your search request…'}</p></div>
      <div className="inspector-grid">
        <article className="source-pane">
          <div className="pane-label"><span>01</span> page source <b>{sourceLines.length ? `${sourceLines.length} lines` : 'waiting…'}</b></div>
          <div className="code-viewport source-viewport">
            {phase !== 'done' && <span className="agent-pointer" aria-hidden="true"><i />agent</span>}
            <pre>
              {!sourceLines.length && <code className="placeholder-line"><i>1</i><span>Waiting for the page to return HTML…</span></code>}
              {sourceLines.slice(0, visibleSourceLines).map((line, index) => (
                <code className={`${index === focusLine && (phase === 'source' || phase === 'fetching') ? 'agent-focus' : ''} ${phase === 'compressing' && index % 4 === 1 ? 'agent-muted' : ''}`} key={`${line.content}-${index}`}>
                  <i>{index + 1}</i><span className="code-content"><span className="code-indent">{'  '.repeat(line.indent)}</span>{highlightHtml(line.content)}</span>{index === focusLine && phase === 'source' && <b className="edit-caret" />}
                </code>
              ))}
              {phase === 'source' && visibleSourceLines < sourceLines.length && <code className="typing-cursor"><i>{visibleSourceLines + 1}</i><span>▌</span></code>}
            </pre>
          </div>
        </article>
        <article className="source-pane compressed-pane">
          <div className="pane-label"><span>02</span> agent draft <b>{phase === 'ai' ? 'comparing…' : candidateLines.length ? `${candidateLines.length} records` : 'not started'}</b></div>
          <div className="code-viewport candidate-viewport">
            <pre>
              {!candidateLines.length && <code className="placeholder-line"><span>{phase === 'fetching' ? '// The agent will rewrite useful nodes here' : '// Reading before making changes…'}</span></code>}
              {candidateLines.slice(0, visibleCandidateLines).map((line, index) => (
                <code className={index === visibleCandidateLines - 1 && (phase === 'compressing' || phase === 'ai') ? 'agent-focus thread-head' : ''} key={`${line}-${index}`}>
                  <span className="change-mark">+</span><FormattedCandidate line={line} />{index === visibleCandidateLines - 1 && phase !== 'done' && <b className="edit-caret" />}
                </code>
              ))}
              {phase === 'compressing' && visibleCandidateLines < candidateLines.length && <code className="typing-cursor"><span>+ ▌</span></code>}
            </pre>
          </div>
        </article>
      </div>
      <p className="inspector-note"><span className="privacy-dot" />The agent removes scripts, styles, metadata, and hidden markup before matching.</p>
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
    <section id="result-output" className="code-block result-block" aria-labelledby="result-title">
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
    <section id="result-output" className="code-block error-block" aria-live="assertive">
      <CodeTag>&lt;<span className="syntax-element">error</span> <span className="syntax-attribute">code</span>=<span className="syntax-string">"{result.code}"</span>&gt;</CodeTag>
      <p>{result.error}</p>
      <CodeTag>&lt;/<span className="syntax-element">error</span>&gt;</CodeTag>
    </section>
  )
}

type SetupGuideProps = {
  step: number
  apiKey: string
  error: string
  validating: boolean
  showKey: boolean
  onStepChange: (step: number) => void
  onApiKeyChange: (value: string) => void
  onShowKeyChange: () => void
  onConnect: (event: FormEvent) => void
}

const guideSteps = ['Give the agent a target', 'Follow the live inspection', 'Connect Gemini']

function SetupGuide({ step, apiKey, error, validating, showKey, onStepChange, onApiKeyChange, onShowKeyChange, onConnect }: SetupGuideProps) {
  const consoleRef = useRef<HTMLElement>(null)

  useEffect(() => {
    const dialog = consoleRef.current
    if (!dialog) return
    dialog.focus()
    function keepFocus(event: globalThis.KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        return
      }
      if (event.key !== 'Tab') return
      const focusable = Array.from(dialog!.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), a[href]'))
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    dialog.addEventListener('keydown', keepFocus)
    return () => dialog.removeEventListener('keydown', keepFocus)
  }, [])

  return (
    <div className="setup-gate" role="dialog" aria-modal="true" aria-labelledby="setup-title" aria-describedby="setup-description">
      <section className="setup-console" ref={consoleRef} tabIndex={-1}>
        <header className="setup-header">
          <div className="setup-brand"><span className="agent-mark" aria-hidden="true"><i />A</span><div><small>SCRAPTED / FIRST RUN</small><strong>Agent setup guide</strong></div></div>
          <div className="setup-counter"><span>GUIDE</span><b>0{step + 1}</b><small>/03</small></div>
        </header>
        <div className="setup-layout">
          <nav className="setup-nav" aria-label="Setup progress">
            {guideSteps.map((label, index) => (
              <button type="button" className={index === step ? 'current' : index < step ? 'complete' : ''} onClick={() => index < step && onStepChange(index)} disabled={index > step || validating} key={label}>
                <span>{index < step ? '✓' : String(index + 1).padStart(2, '0')}</span><b>{label}</b><i />
              </button>
            ))}
          </nav>
          <article className="setup-content">
            {step === 0 && (
              <div className="setup-panel setup-intro">
                <p className="setup-kicker">01 — DEFINE THE JOB</p>
                <h2 id="setup-title">Tell the agent what the page is hiding.</h2>
                <p id="setup-description">Scrapted opens a public webpage, reads its DOM, and finds the exact value you describe.</p>
                <div className="setup-example" aria-label="Example scraping request">
                  <p><span>URL</span><code>https://example.com/products</code></p>
                  <p><span>REQUEST</span><code>Find the price of the first product</code></p>
                  <p><span>SELECTOR</span><code>#product-price <i>optional</i></code></p>
                </div>
                <div className="setup-callout"><b>Write naturally.</b><span>Ask for a title, price, author, date, link, or any visible page detail.</span></div>
              </div>
            )}
            {step === 1 && (
              <div className="setup-panel setup-process">
                <p className="setup-kicker">02 — WATCH THE WORK</p>
                <h2 id="setup-title">The agent shows every decision live.</h2>
                <p id="setup-description">Stay focused on one stage at a time while Scrapted turns noisy HTML into a verified answer.</p>
                <ol className="setup-flow">
                  <li><span>01</span><div><b>Open page</b><small>Fetch the public HTML safely.</small></div></li>
                  <li><span>02</span><div><b>Read markup</b><small>Map useful, visible content.</small></div></li>
                  <li><span>03</span><div><b>Rewrite DOM</b><small>Remove scripts and low-signal nodes.</small></div></li>
                  <li><span>04</span><div><b>Match + verify</b><small>Use Gemini, then check the answer against the page.</small></div></li>
                </ol>
                <div className="setup-callout"><b>Selector recovery.</b><span>If an old CSS selector breaks, the agent can find its replacement.</span></div>
              </div>
            )}
            {step === 2 && (
              <form className="setup-panel setup-key-panel" onSubmit={onConnect}>
                <p className="setup-kicker">03 — REQUIRED CONNECTION</p>
                <h2 id="setup-title">Connect your Gemini API key.</h2>
                <p id="setup-description">Each person uses their own key. Scrapted stays locked until Google verifies it.</p>
                <label className="setup-key-label">
                  <span>Gemini API key</span>
                  <span className="setup-key-field">
                    <input type={showKey ? 'text' : 'password'} value={apiKey} onChange={(event) => onApiKeyChange(event.target.value)} placeholder="Paste your key here" autoComplete="off" autoFocus required disabled={validating} />
                    <button type="button" onClick={onShowKeyChange} aria-label={showKey ? 'Hide API key' : 'Show API key'} disabled={validating}>{showKey ? 'HIDE' : 'SHOW'}</button>
                  </span>
                </label>
                <a className="setup-key-link" href="https://ai.google.dev/gemini-api/docs/api-key" target="_blank" rel="noreferrer"><span>↗</span><b>Get a Gemini API key</b><small>Open Google&apos;s official setup guide</small></a>
                <p className="setup-privacy"><span className="privacy-dot" />Kept only in this browser tab&apos;s session. Never saved to the project or returned by the server.</p>
                {error && <p className="setup-error" role="alert">{error}</p>}
                <button className="setup-connect" type="submit" disabled={validating || !apiKey.trim()}>{validating ? <><span className="button-pulse" />Verifying with Gemini…</> : <>Verify key &amp; enter <span>→</span></>}</button>
              </form>
            )}
          </article>
        </div>
        <footer className="setup-footer">
          <p><span>●</span> Setup required before first scrape</p>
          <div>
            {step > 0 && <button type="button" className="setup-back" onClick={() => onStepChange(step - 1)} disabled={validating}>← Back</button>}
            {step < 2 && <button type="button" className="setup-next" onClick={() => onStepChange(step + 1)}>Continue <span>→</span></button>}
          </div>
        </footer>
      </section>
    </div>
  )
}

export default function App() {
  const [booting, setBooting] = useState(true)
  const [apiKey, setApiKey] = useState(getSessionApiKey)
  const [setupComplete, setSetupComplete] = useState(() => Boolean(getSessionApiKey()))
  const [guideStep, setGuideStep] = useState(0)
  const [guideKey, setGuideKey] = useState(getSessionApiKey)
  const [showGuideKey, setShowGuideKey] = useState(false)
  const [validatingKey, setValidatingKey] = useState(false)
  const [guideError, setGuideError] = useState('')
  const [form, setForm] = useState(initialForm)
  const [result, setResult] = useState<ScrapeResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [clientError, setClientError] = useState('')
  const [inspection, setInspection] = useState<Pick<ScrapeResponse, 'source_preview' | 'compressed_dom'> | null>(null)
  const [inspectionPhase, setInspectionPhase] = useState<InspectionPhase>('done')
  const [progressMessage, setProgressMessage] = useState('Request submitted to Scrapted.')
  const trace = useMemo(() => result?.trace ?? [], [result])
  const displayedPhase = useRef<InspectionPhase>('done')
  const phaseStartedAt = useRef(0)
  const phaseTimer = useRef<number | null>(null)
  const phaseQueue = useRef<Array<{ phase: InspectionPhase; resolve: () => void }>>([])

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setBooting(false)
      return
    }
    const timer = window.setTimeout(() => setBooting(false), 1650)
    return () => window.clearTimeout(timer)
  }, [])

  useEffect(() => {
    if (booting || setupComplete) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = previousOverflow }
  }, [booting, setupComplete])

  useEffect(() => {
    if (inspectionPhase === 'done' && !result) return
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const showingResult = inspectionPhase === 'done'
    const selector = showingResult
      ? '#result-output'
      : inspectionPhase === 'compressing' || inspectionPhase === 'ai'
        ? '#agent-workbench .compressed-pane'
        : inspectionPhase === 'source'
          ? '#agent-workbench .source-pane:first-child'
          : '#agent-workbench .inspector-header'
    const timer = window.setTimeout(() => {
      document.querySelector(selector)?.scrollIntoView({
        behavior: reducedMotion ? 'auto' : 'smooth',
        block: showingResult ? 'start' : 'center',
      })
    }, 80)
    return () => window.clearTimeout(timer)
  }, [inspectionPhase, result])

  useEffect(() => () => {
    if (phaseTimer.current !== null) window.clearTimeout(phaseTimer.current)
    phaseQueue.current.splice(0).forEach((item) => item.resolve())
  }, [])

  function showPhase(phase: InspectionPhase) {
    displayedPhase.current = phase
    phaseStartedAt.current = window.performance.now()
    setInspectionPhase(phase)
  }

  function drainPhaseQueue() {
    if (phaseTimer.current !== null || !phaseQueue.current.length) return
    const elapsed = window.performance.now() - phaseStartedAt.current
    const minimumFocusTime = displayedPhase.current === 'fetching' ? 520 : 640
    phaseTimer.current = window.setTimeout(() => {
      phaseTimer.current = null
      const next = phaseQueue.current.shift()
      if (!next) return
      showPhase(next.phase)
      next.resolve()
      drainPhaseQueue()
    }, Math.max(0, minimumFocusTime - elapsed))
  }

  function queuePhase(phase: InspectionPhase): Promise<void> {
    if (phase === displayedPhase.current || phaseQueue.current.some((item) => item.phase === phase)) return Promise.resolve()
    return new Promise((resolve) => {
      phaseQueue.current.push({ phase, resolve })
      drainPhaseQueue()
    })
  }

  function resetFocusedRun() {
    if (phaseTimer.current !== null) window.clearTimeout(phaseTimer.current)
    phaseTimer.current = null
    phaseQueue.current.splice(0).forEach((item) => item.resolve())
    showPhase('fetching')
  }

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }))
  }

  async function connectApiKey(event: FormEvent) {
    event.preventDefault()
    const candidate = guideKey.trim()
    if (!candidate) {
      setGuideError('Paste your Gemini API key to continue.')
      return
    }
    setGuideError('')
    setValidatingKey(true)
    try {
      await validateApiKey(candidate)
      window.sessionStorage.setItem(apiKeySessionKey, candidate)
      setApiKey(candidate)
      setSetupComplete(true)
      setShowGuideKey(false)
    } catch (error) {
      setGuideError(error instanceof Error ? error.message : 'The API key could not be verified. Try again.')
    } finally {
      setValidatingKey(false)
    }
  }

  function requestNewApiKey(message = '') {
    window.sessionStorage.removeItem(apiKeySessionKey)
    setApiKey('')
    setGuideKey('')
    setGuideStep(2)
    setGuideError(message)
    setSetupComplete(false)
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!apiKey) {
      requestNewApiKey('Connect and verify your Gemini API key before scraping.')
      return
    }
    setClientError('')
    setResult(null)
    setInspection(null)
    resetFocusedRun()
    setProgressMessage('Opening the page and requesting its markup.')
    if (!form.url.trim() || !form.query.trim()) {
      setClientError('Add a public URL and describe the element you want to find.')
      return
    }
    setLoading(true)
    try {
      const response = await scrapeStream({
        url: form.url.trim(),
        query: form.query.trim(),
        expected_selector: form.expectedSelector.trim() || undefined,
      }, apiKey, (update: StreamUpdate) => {
        if (update.type === 'source_ready') {
          setInspection({ source_preview: update.source_preview, compressed_dom: '' })
          void queuePhase('source')
        } else if (update.type === 'compressed_dom') {
          setInspection((current) => ({ source_preview: current?.source_preview ?? '', compressed_dom: update.compressed_dom }))
          void queuePhase('compressing')
        } else {
          setProgressMessage(update.message)
          if (update.type === 'ai_waiting') void queuePhase('ai')
        }
      })
      await queuePhase('done')
      if (!response.success && (response.code === 'INVALID_API_KEY' || response.code === 'API_KEY_REQUIRED')) {
        requestNewApiKey(response.error)
        return
      }
      setResult(response)
    } catch {
      await queuePhase('done')
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
    <main className={`app-shell ${loading ? 'is-running' : ''} ${booting ? 'is-booting' : 'is-ready'}`}>
      {booting && (
        <div className="boot-screen" role="status" aria-live="polite" aria-label="Loading Scrapted workspace">
          <div className="boot-console">
            <div className="boot-meta"><span>SCRAPTED / SYSTEM BOOT</span><b>00—01</b></div>
            <div className="boot-wordmark" aria-hidden="true">scrapted<span>_</span></div>
            <div className="boot-status-line"><span>INIT</span><p>Preparing agent workspace</p><i /></div>
            <div className="boot-progress" aria-hidden="true"><i /></div>
            <div className="boot-log" aria-hidden="true">
              <span><i>01</i>interface modules</span>
              <span><i>02</i>DOM workbench</span>
              <span><i>03</i>agent thread</span>
            </div>
          </div>
        </div>
      )}
      {!booting && !setupComplete && (
        <SetupGuide
          step={guideStep}
          apiKey={guideKey}
          error={guideError}
          validating={validatingKey}
          showKey={showGuideKey}
          onStepChange={(step) => { setGuideStep(step); setGuideError('') }}
          onApiKeyChange={(value) => { setGuideKey(value); setGuideError('') }}
          onShowKeyChange={() => setShowGuideKey((current) => !current)}
          onConnect={connectApiKey}
        />
      )}
      <div className="page-edge-frame" aria-hidden="true">
        <span className="page-edge-label page-edge-label-top">SCRAPTED / LIVE WORKSPACE</span>
        <span className="page-edge-label page-edge-label-bottom">LOCAL SESSION / 01</span>
      </div>
      <aside className="side-rail side-rail-left" aria-hidden="true">
        <span className="rail-coordinate">X—01 / LOCAL</span>
        <div className="rail-brand"><b>scrapted</b><span>DOM AGENT</span></div>
        <div className="rail-signal"><i /><span>private workspace</span></div>
      </aside>
      <aside className="side-rail side-rail-right" aria-hidden="true">
        <div className="rail-run-state"><span>RUN / {loading ? 'ACTIVE' : result ? 'COMPLETE' : 'STANDBY'}</span><i className={loading ? 'active' : ''} /></div>
        <ol className="rail-stages">
          {agentSteps.map((step, index) => {
            const phaseIndex = agentSteps.findIndex((item) => item.phase === inspectionPhase)
            const status = result || inspectionPhase === 'done' && loading
              ? 'complete'
              : loading && index < phaseIndex
                ? 'complete'
                : loading && index === phaseIndex
                  ? 'current'
                  : 'queued'
            return <li className={status} key={step.phase}><i /><span>{String(index + 1).padStart(2, '0')}</span><b>{step.label}</b></li>
          })}
        </ol>
        <span className="rail-coordinate rail-coordinate-bottom">Y—24 / READY</span>
      </aside>
      <div className="editor" aria-label="Scrapted scraping workspace" aria-hidden={!setupComplete || undefined}>
        <header className="editor-tab"><span className="file-dot" aria-hidden="true" />index.html<button type="button" className="api-status" onClick={() => { setGuideKey(apiKey); setGuideStep(2); setGuideError(''); setSetupComplete(false) }} disabled={loading}><i />Gemini connected <span>CHANGE</span></button></header>
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
                    <button className="primary-action" type="submit" disabled={loading}>{loading ? <><span className="button-pulse" aria-hidden="true" />Agent working</> : <>Scrape <span aria-hidden="true">→</span></>}</button>
                  </form>
                  <CodeTag>&lt;/<span className="syntax-element">form</span>&gt;</CodeTag>
                </section>
                <Trace trace={trace} loading={loading} progressMessage={progressMessage} />
                {(loading || inspection || result) && <SourceInspector result={inspection || result || { source_preview: '', compressed_dom: '' }} query={form.query} phase={inspectionPhase} />}
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
