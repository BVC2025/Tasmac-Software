#!/usr/bin/env node
/**
 * Generates the kiosk voice prompts with Sarvam AI text-to-speech (bulbul).
 *
 *   npm run voice                       # generate new / changed clips
 *   npm run voice -- --force            # regenerate everything
 *   npm run voice -- --samples          # one sample per speaker, to choose a voice
 *   npm run voice -- --speaker-ta kavitha --speaker-en priya
 *   npm run voice -- --pace-ta 0.9 --temperature-ta 0.3   # slower, steadier Tamil
 *   npm run voice -- --only insert_bottle
 *   npm run voice -- --lang ta                           # one language only
 *   npm run voice -- --dry-run
 *
 * API key: SARVAM_API_KEY environment variable, or a line SARVAM_API_KEY=... in kiosk/.env.local
 * (git-ignored). The key is only needed here; the kiosk plays the generated files offline.
 */
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const OUT = join(ROOT, 'public', 'voice')
const MANIFEST = join(OUT, 'manifest.json')
const API = 'https://api.sarvam.ai/text-to-speech'
const LANGS = { ta: 'ta-IN', en: 'en-IN' }
const SAMPLE_SPEAKERS = ['kavitha', 'roopa', 'priya', 'shruti', 'gokul', 'vijay', 'mani', 'anand']

// ---------- args ----------
const args = process.argv.slice(2)
const flag = (name) => args.includes(`--${name}`)
const opt = (name, def) => {
  const i = args.indexOf(`--${name}`)
  return i >= 0 && args[i + 1] ? args[i + 1] : def
}

const previous = existsSync(MANIFEST) ? JSON.parse(readFileSync(MANIFEST, 'utf8')) : null
const settings = {
  model: opt('model', previous?.model ?? 'bulbul:v3'),
  speakers: {
    ta: opt('speaker-ta', previous?.speakers?.ta ?? 'kavitha'),
    en: opt('speaker-en', previous?.speakers?.en ?? 'kavitha'),
  },
  // Per language. Tamil defaults are the clearest settings measured (TTS -> STT error rate).
  pace: {
    ta: Number(opt('pace-ta', previous?.pace?.ta ?? 0.9)),
    en: Number(opt('pace-en', previous?.pace?.en ?? 1.0)),
  },
  temperature: {
    ta: Number(opt('temperature-ta', previous?.temperature?.ta ?? 0.3)),
    en: Number(opt('temperature-en', previous?.temperature?.en ?? 0.5)),
  },
  sample_rate: Number(opt('sample-rate', previous?.sample_rate ?? 24000)),
  codec: 'mp3',
}

function apiKey() {
  if (process.env.SARVAM_API_KEY) return process.env.SARVAM_API_KEY.trim()
  const local = join(ROOT, '.env.local')
  if (existsSync(local)) {
    const line = readFileSync(local, 'utf8').split(/\r?\n/).find((l) => l.startsWith('SARVAM_API_KEY='))
    if (line) return line.slice('SARVAM_API_KEY='.length).trim()
  }
  return null
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function tts(key, text, lang, speaker) {
  const body = {
    text,
    language_code: LANGS[lang],
    model: settings.model,
    speaker,
    pace: settings.pace[lang],
    temperature: settings.temperature[lang],
    speech_sample_rate: settings.sample_rate,
    output_audio_codec: settings.codec,
  }
  for (let attempt = 1; ; attempt++) {
    const res = await fetch(API, {
      method: 'POST',
      headers: { 'api-subscription-key': key, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (res.ok) {
      const data = await res.json()
      if (!data.audios?.length) throw new Error('No audio in response')
      return Buffer.concat(data.audios.map((a) => Buffer.from(a, 'base64')))
    }
    const detail = await res.text()
    if ((res.status === 429 || res.status >= 500) && attempt < 5) {
      const wait = 1000 * 2 ** attempt
      console.warn(`  ${res.status}, retrying in ${wait / 1000}s…`)
      await sleep(wait)
      continue
    }
    if (res.status === 401 || res.status === 403) throw new Error(`Sarvam rejected the API key (${res.status}): ${detail}`)
    if (res.status === 402) throw new Error('Sarvam account has no credits left - add credits at dashboard.sarvam.ai and run again (finished clips are kept).')
    throw new Error(`Sarvam API ${res.status}: ${detail}`)
  }
}

const hash = (text, lang) =>
  createHash('sha1')
    .update(JSON.stringify([text, settings.model, settings.speakers[lang], settings.pace[lang], settings.temperature[lang], settings.sample_rate]))
    .digest('hex')
    .slice(0, 12)

async function main() {
  const { prompts } = JSON.parse(readFileSync(join(ROOT, 'voice-prompts.json'), 'utf8'))
  const key = apiKey()
  const dry = flag('dry-run')
  if (!key && !dry) {
    console.error('Missing SARVAM_API_KEY. Put SARVAM_API_KEY=your-key in kiosk/.env.local (or set the environment variable).')
    process.exit(1)
  }

  if (flag('samples')) {
    const dir = join(OUT, '_samples')
    mkdirSync(dir, { recursive: true })
    for (const lang of Object.keys(LANGS)) {
      for (const sp of SAMPLE_SPEAKERS) {
        const file = join(dir, `${lang}_${sp}.mp3`)
        console.log(`sample ${lang} ${sp}`)
        if (!dry) writeFileSync(file, await tts(key, prompts.insert_bottle[lang], lang, sp))
      }
    }
    console.log(`Samples in ${dir}. Pick one and run: npm run voice -- --speaker-ta <name> --speaker-en <name>`)
    return
  }

  const only = opt('only', null)
  const force = flag('force')
  const clips = previous && previous.model === settings.model ? { ...previous.clips } : {}
  let made = 0
  let skipped = 0
  const langFilter = opt('lang', null) // e.g. --lang ta : regenerate Tamil only
  for (const [id, texts] of Object.entries(prompts)) {
    if (only && id !== only) continue
    for (const lang of Object.keys(LANGS)) {
      if (langFilter && lang !== langFilter) continue
      const text = texts[lang]
      if (!text) continue
      if (text.length > 2500) throw new Error(`${id}.${lang} is longer than 2500 characters`)
      const h = hash(text, lang)
      const file = join(OUT, lang, `${id}.mp3`)
      if (!force && clips[id]?.[lang] === h && existsSync(file)) {
        skipped++
        continue
      }
      console.log(`${dry ? '[dry-run] ' : ''}${lang} ${id} (${settings.speakers[lang]})`)
      if (!dry) {
        mkdirSync(dirname(file), { recursive: true })
        writeFileSync(file, await tts(key, text, lang, settings.speakers[lang]))
        clips[id] = { ...clips[id], [lang]: h }
        writeFileSync(MANIFEST, JSON.stringify({ ...settings, generated_at: new Date().toISOString(), clips }, null, 2))
        await sleep(150)
      }
      made++
    }
  }
  // drop clips that were removed from voice-prompts.json
  for (const id of Object.keys(clips)) if (!prompts[id]) delete clips[id]

  if (!dry) {
    mkdirSync(OUT, { recursive: true })
    writeFileSync(MANIFEST, JSON.stringify({ ...settings, generated_at: new Date().toISOString(), clips }, null, 2))
  }
  console.log(`Done: ${made} generated, ${skipped} unchanged. Voice: ta=${settings.speakers.ta} (pace ${settings.pace.ta}, temp ${settings.temperature.ta}), en=${settings.speakers.en} (pace ${settings.pace.en}), ${settings.model}`)
}

main().catch((e) => {
  console.error(e.message)
  process.exit(1)
})
