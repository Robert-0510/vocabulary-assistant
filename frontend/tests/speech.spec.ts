import { describe, expect, it, vi } from 'vitest'

describe('speech fallback', () => {
  it('uses the Youdao audio endpoint when Web Speech is unavailable', async () => {
    Object.defineProperty(window, 'speechSynthesis', {
      value: undefined,
      configurable: true,
    })
    const created: string[] = []
    class AudioStub {
      src: string
      constructor(src: string) {
        this.src = src
        created.push(src)
      }
      play() {
        return Promise.resolve()
      }
    }
    vi.stubGlobal('Audio', AudioStub)

    const { pronounce } = await import('@/utils/speech')
    pronounce('abandon')

    expect(created).toHaveLength(1)
    expect(created[0]).toContain('dict.youdao.com')
    expect(created[0]).toContain('abandon')
  })
})
