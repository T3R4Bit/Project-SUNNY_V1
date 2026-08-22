import { createAvatar } from '@bible-strong/avatar-web'

import definition from './strobi.avatar.json'
import './styles.css'

// avatar-web reads window.matchMedia('(prefers-reduced-motion: reduce)') on
// every frame and, when it matches, skips ALL transition easing and hard-cuts
// between expressions instead of tweening -- that's very likely why this
// looked "framy" rather than smooth. There's no option on createAvatar() to
// override it directly, so we shim matchMedia for just that one query before
// createAvatar ever reads it. Deliberate for this project: it's a dedicated
// always-on face display, not a page that should defer to a system-wide
// accessibility toggle.
const realMatchMedia = window.matchMedia?.bind(window)
if (realMatchMedia) {
  window.matchMedia = (query: string): MediaQueryList => {
    if (query.includes('prefers-reduced-motion')) {
      return {
        matches: false,
        media: query,
        onchange: null,
        addListener() {},
        removeListener() {},
        addEventListener() {},
        removeEventListener() {},
        dispatchEvent: () => false,
      }
    }
    return realMatchMedia(query)
  }
}

// Placeholder character ("Strobi", from the bible-strong-avatar-lab repo's own
// example) until a custom character is designed in the visual editor. Real
// state names to build/test the state machine against, not the final look.

const avatar = createAvatar('#avatar', {
  definition,
  defaultAnimation: 'idle',
  size: '100%',
})

const stateReadout = document.querySelector<HTMLSpanElement>('#state-readout')!

function setState(state: string) {
  avatar.play(state)
  stateReadout.textContent = state
}

document.querySelectorAll<HTMLButtonElement>('[data-state]').forEach(button => {
  button.addEventListener('click', () => setState(button.dataset.state!))
})

// Emotion presets are themselves full animations on this character (not bare
// expressions), so they're triggered the same way as the core states above.
document.querySelectorAll<HTMLButtonElement>('[data-emotion]').forEach(button => {
  button.addEventListener('click', () => setState(button.dataset.emotion!))
})

// --- Server connection (Phase 6 endpoint: sunny_code/components/pi_companion.py) ---
//
// On the real device, the Python wake-word client (Phase 5) is what holds
// the connection to the server and streams mic audio -- this page would just
// receive relayed state/audio from that local client, not talk to the
// server directly. For now, before that Python piece exists, this page
// connects straight to /ws/pi itself so the whole loop (state machine +
// real TTS audio + amplitude reaction) can be tested here in a browser.
//
// avatar-web's public API is animation-based (play/setExpression), with no
// raw parameter control and no mouth geometry on this character at all --
// so "amplitude-driven speaking" is implemented as an external CSS pulse
// (--speak-pulse custom property on #avatar) layered on top of whichever
// named animation is already looping, not an internal morph.

const avatarHost = document.querySelector<HTMLDivElement>('#avatar')!
const wsUrlInput = document.querySelector<HTMLInputElement>('#ws-url')!
const wsConnectButton = document.querySelector<HTMLButtonElement>('#ws-connect')!
const wsStatus = document.querySelector<HTMLSpanElement>('#ws-status')!

let socket: WebSocket | null = null
let audioContext: AudioContext | null = null

function setWsStatus(text: string) {
  wsStatus.textContent = text
}

function getAudioContext(): AudioContext {
  if (!audioContext) audioContext = new AudioContext()
  return audioContext
}

async function playReplyAudio(wavBytes: ArrayBuffer) {
  const ctx = getAudioContext()
  const buffer = await ctx.decodeAudioData(wavBytes)

  const analyser = ctx.createAnalyser()
  analyser.fftSize = 256
  const levels = new Uint8Array(analyser.frequencyBinCount)

  const source = ctx.createBufferSource()
  source.buffer = buffer
  source.connect(analyser)
  analyser.connect(ctx.destination)

  let pulsing = true
  const pulse = () => {
    if (!pulsing) return
    analyser.getByteTimeDomainData(levels)
    let sumSquares = 0
    for (const level of levels) {
      const centered = (level - 128) / 128
      sumSquares += centered * centered
    }
    const rms = Math.sqrt(sumSquares / levels.length)
    // Subtle: full-volume speech should nudge scale by a few percent, not
    // visibly distort the character.
    avatarHost.style.setProperty('--speak-pulse', (1 + Math.min(rms, 1) * 0.06).toFixed(4))
    requestAnimationFrame(pulse)
  }

  source.onended = () => {
    pulsing = false
    avatarHost.style.setProperty('--speak-pulse', '1')
  }

  source.start()
  requestAnimationFrame(pulse)
}

function connect() {
  const url = wsUrlInput.value.trim()
  if (!url) return
  socket = new WebSocket(url)
  socket.binaryType = 'arraybuffer'
  setWsStatus('connecting…')

  socket.addEventListener('open', () => {
    setWsStatus('connected')
    wsConnectButton.textContent = 'Disconnect'
  })
  socket.addEventListener('close', () => {
    setWsStatus('disconnected')
    wsConnectButton.textContent = 'Connect'
    socket = null
  })
  socket.addEventListener('error', () => setWsStatus('error'))

  socket.addEventListener('message', event => {
    if (typeof event.data === 'string') {
      const message = JSON.parse(event.data) as { state?: string; emotion?: string }
      if (message.emotion) setState(message.emotion)
      else if (message.state) setState(message.state)
    } else {
      void playReplyAudio(event.data as ArrayBuffer)
    }
  })
}

function disconnect() {
  socket?.close()
  socket = null
}

wsConnectButton.addEventListener('click', () => {
  if (socket) disconnect()
  else connect()
})
