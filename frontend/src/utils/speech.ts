/**
 * 单词发音：浏览器 Web Speech API 优先，无英文语音/不可用时回退有道词典真人发音。
 */

function hasEnVoice(): boolean {
  const synth = window.speechSynthesis
  if (!synth) return false
  return synth.getVoices().some((v) => v.lang.toLowerCase().startsWith('en'))
}

// 提前预热语音列表（Chrome 异步加载）
if (typeof window !== 'undefined' && window.speechSynthesis) {
  window.speechSynthesis.getVoices()
  window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices()
}

function playYoudao(word: string): void {
  const url = `https://dict.youdao.com/dictvoice?type=1&audio=${encodeURIComponent(word)}`
  const audio = new Audio(url)
  audio.play().catch(() => {
    /* 网络不可用则静默失败 */
  })
}

export function pronounce(word: string): void {
  const synth = window.speechSynthesis
  if (synth && hasEnVoice()) {
    const utter = new SpeechSynthesisUtterance(word)
    const voices = synth.getVoices().filter((v) => v.lang.toLowerCase().startsWith('en'))
    utter.voice = voices.find((v) => v.lang === 'en-US') || voices[0]
    utter.lang = 'en-US'
    utter.rate = 0.9
    synth.cancel()
    synth.speak(utter)
    return
  }
  playYoudao(word)
}
