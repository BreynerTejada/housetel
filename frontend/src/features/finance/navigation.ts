/** Full-page navigation away from the SPA (back to the hotel after the simulated gateway). */
export function leavePage(url: string): void {
  window.location.assign(url)
}
