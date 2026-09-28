/** Legal files (invoice PDF/XML, SIRE TXT) come from the staff API with `X-Property-Id`, so they are fetched as
 * blobs and then saved or shown; a plain link could not send the header. */

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/**
 * Opens a PDF in a new tab. The tab is opened synchronously (inside the click) so pop-up blockers allow it, then
 * pointed at the file when it arrives; if the browser still blocks it, the file is downloaded instead.
 */
export async function openBlobInTab(load: () => Promise<Blob>, filename: string): Promise<void> {
  const tab = window.open('', '_blank')
  try {
    const blob = await load()
    if (!tab || tab.closed) {
      saveBlob(blob, filename)
      return
    }
    const url = URL.createObjectURL(blob)
    tab.location.href = url
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
  } catch (error) {
    tab?.close()
    throw error
  }
}
