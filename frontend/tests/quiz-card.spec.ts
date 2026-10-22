import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import QuizCard from '@/components/QuizCard.vue'
import type { StudyWord } from '@/api/types'

vi.mock('@/utils/speech', () => ({ pronounce: vi.fn() }))

const ElButton = {
  name: 'ElButton',
  emits: ['click'],
  template: '<button @click="$emit(\'click\')"><slot /></button>',
}
const ElTag = { template: '<span><slot /></span>' }
const ElText = { template: '<span><slot /></span>' }

const word: StudyWord = {
  id: 1,
  spelling: 'abandon',
  phonetic: '/əˈbændən/',
  definition: 'v. 放弃',
  example_en: null,
  example_cn: null,
  status: 'new',
  quiz: {
    type: 'cn2en',
    question: 'v. 放弃',
    options: ['abandon', 'benefit', 'crucial', 'emerge'],
    answer_index: 0,
  },
}

function render() {
  return mount(QuizCard, {
    props: {
      word,
      quiz: word.quiz!,
      label: '新词测试',
    },
    global: {
      components: { ElButton, ElTag, ElText },
      stubs: { PronounceButton: true },
    },
  })
}

describe('QuizCard', () => {
  it('announces a correct answer through an aria-live region', async () => {
    const wrapper = render()
    await wrapper.findAll('button')[0].trigger('click')

    const feedback = wrapper.find('[role="status"]')
    expect(feedback.exists()).toBe(true)
    expect(feedback.attributes('aria-live')).toBe('polite')
    expect(feedback.text()).toContain('回答正确')
  })

  it('shows the correct answer after a wrong pick', async () => {
    const wrapper = render()
    await wrapper.findAll('button')[1].trigger('click')

    const feedback = wrapper.find('[role="status"]')
    expect(feedback.text()).toContain('回答错误')
    expect(feedback.text()).toContain('abandon')
  })
})
