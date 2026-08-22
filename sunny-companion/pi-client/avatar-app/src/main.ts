import { createAvatar } from '@bible-strong/avatar-web'

import definition from './strobi.avatar.json'
import './styles.css'

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

// --- Not built yet (Phase 5/6) ---
// This page will eventually open a WebSocket to the local server endpoint
// and drive `setState()` from incoming {"state": ...} / {"emotion": ...}
// messages instead of button clicks, and the "speaking" state's animation
// should be modulated by the live TTS audio's amplitude in real time rather
// than looping at the fixed cadence baked into the JSON above — this
// character format has no mouth geometry, so that modulation will act on
// eye/body motion instead of a mouth shape.
