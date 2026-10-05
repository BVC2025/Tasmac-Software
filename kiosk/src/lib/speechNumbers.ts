/**
 * Convert spoken digits (Tamil script, Tamil in English letters, or English)
 * into a digit string. Handles "double 9" / "triple 0".
 *
 *   "nine eight double seven"       -> "9877"
 *   "ஒன்பது எட்டு ஏழு"              -> "987"
 *   "onbadhu ettu rendu"            -> "982"
 *   "98765 43210"                   -> "9876543210"
 */
const WORDS: Record<string, string> = {
  // English
  zero: '0', oh: '0', o: '0', one: '1', won: '1', two: '2', to: '2', too: '2', three: '3', tree: '3',
  four: '4', for: '4', five: '5', six: '6', seven: '7', eight: '8', ate: '8', nine: '9',
  // Tamil in English letters
  poojyam: '0', pujyam: '0', sunyam: '0', onnu: '1', ondru: '1', rendu: '2', irandu: '2', moonu: '3',
  moondru: '3', naalu: '4', nalu: '4', naangu: '4', anju: '5', ainthu: '5', aaru: '6', aru: '6',
  ezhu: '7', elu: '7', ettu: '8', onbadhu: '9', onbathu: '9',
  // Tamil script
  'பூஜ்ஜியம்': '0', 'பூஜ்யம்': '0', 'சுழியம்': '0', 'சைபர்': '0', 'ஜீரோ': '0',
  'ஒன்று': '1', 'ஒன்னு': '1', 'ஒண்ணு': '1', 'இரண்டு': '2', 'ரெண்டு': '2', 'மூன்று': '3', 'மூணு': '3',
  'நான்கு': '4', 'நாலு': '4', 'ஐந்து': '5', 'அஞ்சு': '5', 'ஆறு': '6', 'ஏழு': '7', 'எட்டு': '8',
  'ஒன்பது': '9',
}
const REPEAT: Record<string, number> = {
  double: 2, dabal: 2, 'டபுள்': 2, triple: 3, tripple: 3, 'ட்ரிபிள்': 3, 'டிரிபிள்': 3,
}

export function spokenToDigits(text: string): string {
  const tokens = text.toLowerCase().replace(/[,.-]/g, ' ').split(/\s+/).filter(Boolean)
  let out = ''
  let repeat = 1
  for (const tok of tokens) {
    if (REPEAT[tok]) {
      repeat = REPEAT[tok]
      continue
    }
    let digits = ''
    if (/^\d+$/.test(tok)) digits = tok
    else if (WORDS[tok]) digits = WORDS[tok]
    else continue
    // "double 9" repeats only the next single digit
    out += digits.length === 1 ? digits.repeat(repeat) : digits
    repeat = 1
  }
  return out
}
