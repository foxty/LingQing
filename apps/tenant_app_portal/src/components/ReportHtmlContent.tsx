import DocumentProse from '@/components/DocumentProse'
import { MarkdownImage } from '@/components/markdown/MarkdownImage'
import { createElement, type ReactNode } from 'react'

const ALLOWED_ATTRS: Record<string, string> = {
  class: 'className',
  href: 'href',
  src: 'src',
  alt: 'alt',
  title: 'title',
  id: 'id',
}

function elementProps(element: Element): Record<string, string> {
  const props: Record<string, string> = {}
  for (const [attr, reactName] of Object.entries(ALLOWED_ATTRS)) {
    const value = element.getAttribute(attr)
    if (value) {
      props[reactName] = value
    }
  }
  return props
}

function nodeToReact(node: Node, key: string | number): ReactNode {
  if (node.nodeType === Node.TEXT_NODE) {
    return node.textContent
  }
  if (node.nodeType !== Node.ELEMENT_NODE) {
    return null
  }

  const element = node as Element
  const tag = element.tagName.toLowerCase()
  if (tag === 'img') {
    return (
      <MarkdownImage
        key={key}
        src={element.getAttribute('src') ?? undefined}
        alt={element.getAttribute('alt') ?? undefined}
      />
    )
  }

  const children = Array.from(element.childNodes)
    .map((child, index) => nodeToReact(child, `${key}-${index}`))
    .filter((child) => child !== null)

  if (tag === 'br' || tag === 'hr') {
    return createElement(tag, { key, ...elementProps(element) })
  }

  return createElement(tag, { key, ...elementProps(element) }, ...children)
}

type ReportHtmlContentProps = {
  html: string
}

export default function ReportHtmlContent({ html }: ReportHtmlContentProps) {
  const container = document.createElement('div')
  container.innerHTML = html
  const body = Array.from(container.childNodes)
    .map((node, index) => nodeToReact(node, index))
    .filter((node) => node !== null)

  return <DocumentProse>{body.length > 0 ? body : null}</DocumentProse>
}
