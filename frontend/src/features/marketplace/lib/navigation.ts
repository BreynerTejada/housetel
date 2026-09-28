/** Leaves the app for the payment gateway (Wompi, or the simulated gateway). Kept apart so tests can replace it. */
export function goToPayment(url: string): void {
  window.location.assign(url)
}
