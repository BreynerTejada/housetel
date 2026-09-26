import { Component, type ErrorInfo, type ReactNode } from 'react'

/** Keeps an optional piece of UI (e.g. the public chat widget) from taking the whole page down. */
export class ErrorBoundary extends Component<{ children: ReactNode; fallback?: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error('UI section failed', error, info.componentStack)
  }

  render() {
    return this.state.failed ? (this.props.fallback ?? null) : this.props.children
  }
}
