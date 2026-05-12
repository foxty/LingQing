import type { Layout } from 'react-grid-layout'

/**
 * Resolve grid layout with a "right-first" packing strategy.
 *
 * Behavior:
 * - Keep the actively moved widget fixed at its drop position.
 * - For any collisions, try to place other widgets by scanning to the right
 *   first; when the row overflows, move to the next row.
 * - This yields minimal vertical movement and predictable reflow.
 */
export function resolveLayoutRightFirst(
  baseLayout: Layout[],
  updatedLayout: Layout[],
  cols: number,
  movedIdOverride?: string | null
): Layout[] {
  if (baseLayout.length === 0) {
    return updatedLayout
  }

  const baseById = new Map(baseLayout.map((item) => [item.i, item]))
  const updatedById = new Map(updatedLayout.map((item) => [item.i, item]))

  const movedId =
    movedIdOverride ??
    updatedLayout.find((item) => {
      const base = baseById.get(item.i)
      if (!base) {
        return true
      }
      return base.x !== item.x || base.y !== item.y || base.w !== item.w || base.h !== item.h
    })?.i

  if (!movedId) {
    return baseLayout
  }

  const movedItem = updatedById.get(movedId) ?? baseById.get(movedId)
  if (!movedItem) {
    return baseLayout
  }

  const clampX = (item: Layout) => {
    const maxX = Math.max(0, cols - item.w)
    return { ...item, x: Math.min(item.x, maxX) }
  }

  const overlaps = (a: Layout, b: Layout) => {
    return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y
  }

  const placed: Layout[] = []
  placed.push(clampX(movedItem))

  const placeItemRightFirst = (item: Layout) => {
    let x = item.x
    let y = item.y

    const candidateBase = { ...item }
    while (true) {
      if (x + item.w > cols) {
        x = 0
        y += 1
        continue
      }

      const candidate = { ...candidateBase, x, y }
      if (!placed.some((existing) => overlaps(candidate, existing))) {
        placed.push(candidate)
        return
      }

      x += 1
    }
  }

  baseLayout.forEach((item) => {
    if (item.i === movedId) {
      return
    }
    const source = baseById.get(item.i) ?? updatedById.get(item.i) ?? item
    placeItemRightFirst(clampX(source))
  })

  return placed
}
