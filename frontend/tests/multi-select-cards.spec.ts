import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import EquivGroupCard from '@/components/EquivGroupCard.vue'
import MeaningMultiCard from '@/components/MeaningMultiCard.vue'
import type { GradedAnswer, MultiQuiz, StudyWord } from '@/api/types'

vi.mock('@/utils/speech', () => ({ pronounce: vi.fn() }))

const ElButton = {
  name: 'ElButton',
  props: ['disabled', 'type', 'plain'],
  emits: ['click'],
  template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
}
const ElTag = { template: '<span><slot /></span>' }
const ElText = { template: '<span><slot /></span>' }

const meaningQuiz: MultiQuiz = {
  type: 'meaning_multi',
  question: 'manifest',
  options: [
    { id: 1, text: '明显的' },
    { id: 2, text: '显示' },
    { id: 3, text: '放弃' },
    { id: 4, text: '好处' },
    { id: 5, text: '出现' },
  ],
  option_count: 5,
}

const word: StudyWord = {
  id: 1,
  spelling: 'manifest',
  phonetic: '/ˈmænɪfest/',
  definition: 'adj. 明显的 v. 显示',
  example_en: null,
  example_cn: null,
  status: 'new',
  quiz: meaningQuiz,
}

function mountMeaning(graded: GradedAnswer | null = null) {
  return mount(MeaningMultiCard, {
    props: { word, quiz: meaningQuiz, label: '新词释义', graded },
    global: {
      components: { ElButton, ElTag, ElText },
      stubs: { PronounceButton: true },
    },
  })
}

function mountEquiv(graded: GradedAnswer | null = null) {
  const quiz: MultiQuiz = {
    ...meaningQuiz,
    type: 'equiv_group',
    question: 'evident',
    options: [
      { id: 11, text: 'manifest' },
      { id: 12, text: 'obvious' },
      { id: 13, text: 'abandon' },
      { id: 14, text: 'benefit' },
    ],
    option_count: 4,
  }
  return mount(EquivGroupCard, {
    props: {
      word: { ...word, id: 2, spelling: 'evident', definition: '明显的', quiz },
      quiz,
      label: '等价组',
      graded,
    },
    global: {
      components: { ElButton, ElTag, ElText },
      stubs: { PronounceButton: true },
    },
  })
}

describe('MeaningMultiCard', () => {
  it('submits every selected sense id', async () => {
    const wrapper = mountMeaning()
    await wrapper.find('[data-option-id="1"]').trigger('click')
    await wrapper.find('[data-option-id="2"]').trigger('click')
    expect(wrapper.find('[data-option-id="1"]').attributes('aria-pressed')).toBe('true')

    await wrapper.find('[data-test="submit"]').trigger('click')
    expect(wrapper.emitted('submit')).toEqual([[[1, 2]]])

    wrapper.unmount()
  })

  it('supports keyboard toggle + Enter submit', async () => {
    const wrapper = mountMeaning()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '2' }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '3' }))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('submit')).toEqual([[[2, 3]]])
    wrapper.unmount()
  })

  it('announces partial results and shows missed options', async () => {
    const wrapper = mountMeaning({
      result: 'partial',
      selectedIds: [1],
      correctIds: [1, 2],
      correctTotal: 2,
      selectedCorrect: 1,
    })
    const panel = wrapper.find('[data-test="sense-result"]')
    expect(panel.exists()).toBe(true)
    expect(panel.attributes('aria-live')).toBe('polite')
    expect(panel.text()).toContain('部分正确')
    expect(wrapper.find('[data-test="missed"]').text()).toContain('显示')

    const next = wrapper.findAll('button').find((button) => button.text().includes('继续'))
    expect(next).toBeTruthy()
    await next!.trigger('click')
    expect(wrapper.emitted('next')).toHaveLength(1)
    wrapper.unmount()
  })
})

describe('EquivGroupCard', () => {
  it('submits selected synonyms and renders the result panel', async () => {
    const wrapper = mountEquiv()
    await wrapper.find('[data-option-id="11"]').trigger('click')
    await wrapper.find('[data-option-id="12"]').trigger('click')
    await wrapper.find('[data-test="submit"]').trigger('click')
    expect(wrapper.emitted('submit')).toEqual([[[11, 12]]])

    await wrapper.setProps({
      graded: {
        result: 'correct',
        selectedIds: [11, 12],
        correctIds: [11, 12],
        correctTotal: 2,
        selectedCorrect: 2,
      },
    })
    const panel = wrapper.find('[data-test="sense-result"]')
    expect(panel.text()).toContain('全部选对')
    expect(wrapper.find('[data-test="submit"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
})
