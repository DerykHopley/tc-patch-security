import { cvePath, followLink, FROM_LIST, openPath } from '../route.ts'

// A CVE id as a link to its own page (B35), in the app: the list, the dashboard's Top 5, alerts, refresh runs and
// the chat all use it, so a CVE opens the same way everywhere. A modified click (new tab) is left to the browser.
// fromList: opened from the CVEs list, which keeps its place first, so the page's back link can return to it in place.
export function CveLink({ id, className, fromList }: { id: string; className?: string; fromList?: () => void }) {
  return (
    <a
      className={className}
      href={cvePath(id)}
      onClick={(e) =>
        followLink(e, (href) => {
          fromList?.()
          openPath(href, fromList ? FROM_LIST : null)
        })
      }
    >
      {id}
    </a>
  )
}
