import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { errorMessage } from '@/lib/errors'
import { fetchInvoiceFile, fetchSireFile, type InvoiceDetail, type SireReport } from './api'
import { openBlobInTab, saveBlob } from './lib/files'
import { invoiceFileName } from './lib/labels'

type InvoiceRef = Pick<InvoiceDetail, 'id' | 'kind' | 'number'>

/** PDF (opened in a new tab) and XML (downloaded) of an invoice, with a busy flag and error toasts. */
export function useInvoiceFiles() {
  const { t } = useTranslation('compliance')
  const [busy, setBusy] = useState<'pdf' | 'xml' | null>(null)
  async function run(invoice: InvoiceRef, format: 'pdf' | 'xml', open = false) {
    setBusy(format)
    try {
      const name = invoiceFileName(invoice.kind, invoice.number, format)
      if (open) await openBlobInTab(() => fetchInvoiceFile(invoice.id, format), name)
      else saveBlob(await fetchInvoiceFile(invoice.id, format), name)
    } catch (error) {
      toast.error(errorMessage(error, t))
    } finally {
      setBusy(null)
    }
  }
  return { busy, openPdf: (invoice: InvoiceRef) => run(invoice, 'pdf', true), download: run }
}

/** Downloads a SIRE file (TXT) with its name. */
export function useSireDownload() {
  const { t } = useTranslation('compliance')
  const [busy, setBusy] = useState<string | null>(null)
  async function download(report: Pick<SireReport, 'id' | 'file_name'>) {
    setBusy(report.id)
    try {
      saveBlob(await fetchSireFile(report.id), report.file_name || 'sire.txt')
    } catch (error) {
      toast.error(errorMessage(error, t))
    } finally {
      setBusy(null)
    }
  }
  return { busy, download }
}

export function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay)
    return () => window.clearTimeout(timer)
  }, [value, delay])
  return debounced
}
