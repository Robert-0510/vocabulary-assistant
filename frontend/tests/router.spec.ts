import { describe, expect, it } from 'vitest'
import router from '@/router'

describe('router', () => {
  it('registers a catch-all page for unknown routes', () => {
    const notFound = router.getRoutes().find((route) => route.name === 'not-found')
    expect(notFound).toBeTruthy()
    expect(notFound?.path).toBe('/:pathMatch(.*)*')
  })

  it('keeps every protected page behind the auth guard', () => {
    const protectedNames = ['study', 'books', 'stats', 'settings']
    for (const name of protectedNames) {
      expect(router.getRoutes().find((route) => route.name === name)?.meta.requiresAuth).toBe(true)
    }
  })
})
