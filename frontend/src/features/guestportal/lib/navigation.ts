/** Full-page navigation to the payment gateway (Wompi or the simulated one). Mocked in tests. */
export function goTo(url: string): void {
  window.location.assign(url)
}
