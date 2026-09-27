/**
 * Guests CRM data layer (backend `/api/v1/guests/`, see docs/integration-notes/B3-guests-team.md).
 * Guests belong to the organization: every property of a chain shares them.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Query } from '@/lib/api'

// ---- Types (exact API shapes) -------------------------------------------------------------------

export type DocumentType = 'CC' | 'CE' | 'PA' | 'TI' | 'PEP' | 'PPT' | 'DNI' | 'NIT' | 'OTHER'
export type Gender = 'F' | 'M' | 'X'
export type DuplicateReason = 'document' | 'email' | 'phone_name'
export type DocumentKind = 'id_front' | 'id_back' | 'passport' | 'signature' | 'other'

export const DOCUMENT_TYPES: DocumentType[] = ['CC', 'CE', 'PA', 'TI', 'PEP', 'PPT', 'DNI', 'NIT', 'OTHER']
export const DOCUMENT_KINDS: DocumentKind[] = ['id_front', 'id_back', 'passport', 'signature', 'other']

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

/** Row of `GET guests/` (also what GuestPicker hands to its consumer for an existing guest). */
export interface GuestSummary {
  id: string
  first_name: string
  last_name: string
  full_name: string
  email: string
  phone: string
  document_type: DocumentType | ''
  document_number: string
  nationality: string
  country_of_residence: string
  city_of_residence: string
  language: string
  is_vip: boolean
  blacklisted: boolean
  tags: string[]
  is_foreign_non_resident: boolean
  anonymized_at: string | null
  stays_count: number | null
  reservations_count: number | null
  last_stay_date: string | null
  created_at: string
}

export interface StayRef {
  reservation_id: string
  code: string
  property_id: string
  property_name: string
  checkin: string
  checkout: string
  status: string
}

export interface GuestStats {
  reservations_count: number
  stays_count: number
  nights: number
  total_spent: string
  cancellations: number
  no_shows: number
  last_stay: StayRef | null
  next_stay: StayRef | null
}

export interface Guest extends GuestSummary {
  birth_date: string | null
  gender: Gender | ''
  address: string
  notes: string
  preferences: Record<string, string>
  marketing_consent: boolean
  data_processing_consent_at: string | null
  custom_values: Record<string, unknown>
  merged_into: string | null
  updated_at: string
  stats: GuestStats
  documents_count: number
}

export interface DuplicateGuest extends GuestSummary {
  reasons: DuplicateReason[]
}

export interface GuestDocument {
  id: string
  guest: string
  kind: DocumentKind
  uploaded_via: 'staff' | 'portal'
  created_at: string
  /** Authenticated endpoint (`/api/v1/guests/documents/<id>/file/`), never a public /media URL. */
  file_url: string
  content_type: string
  filename: string
  size: number | null
}

export interface GuestStay {
  id: string
  code: string
  status: string
  source: string
  channel_code: string
  checkin: string
  checkout: string
  nights: number
  adults: number
  children: number
  total_amount: string
  currency: string
  property: { id: string; name: string }
  role: 'booker' | 'occupant'
  rooms: string[]
}

/**
 * A guest that does not exist yet (same fields as backend `apps.guests.types.GuestInput`). Booking flows
 * send it as the booker/occupant; the backend upserts it (by document, then email).
 */
export interface GuestInput {
  first_name: string
  last_name: string
  email?: string
  phone?: string
  document_type?: DocumentType | ''
  document_number?: string
  nationality?: string
  country_of_residence?: string
  city_of_residence?: string
  birth_date?: string | null
  language?: string
  marketing_consent?: boolean
  data_processing_consent?: boolean
}

/** What GuestPicker returns: an existing guest (has `id`) or a new one to create (GuestInput). */
export type GuestPickerValue = GuestSummary | GuestInput

export function isExistingGuest(value: GuestPickerValue | null | undefined): value is GuestSummary {
  return Boolean(value && 'id' in value && value.id)
}

/** Writable fields of `POST/PATCH guests/`. */
export interface GuestPayload {
  first_name?: string
  last_name?: string
  email?: string
  phone?: string
  document_type?: DocumentType | ''
  document_number?: string
  nationality?: string
  country_of_residence?: string
  city_of_residence?: string
  birth_date?: string | null
  gender?: Gender | ''
  address?: string
  language?: string
  is_vip?: boolean
  blacklisted?: boolean
  tags?: string[]
  notes?: string
  preferences?: Record<string, string>
  marketing_consent?: boolean
  /** true records the Habeas Data consent (now), false revokes it. */
  data_processing_consent?: boolean
  custom_values?: Record<string, unknown>
}

export interface GuestListParams extends Query {
  q?: string
  is_vip?: boolean
  nationality?: string
  tag?: string
  has_stays?: boolean
  ordering?: string
  page?: number
  page_size?: number
}

// ---- Query keys ---------------------------------------------------------------------------------

export const guestKeys = {
  all: ['guests'] as const,
  list: (params: GuestListParams) => ['guests', 'list', params] as const,
  search: (q: string) => ['guests', 'search', q] as const,
  lookup: (params: Record<string, string>) => ['guests', 'lookup', params] as const,
  tags: () => ['guests', 'tags'] as const,
  detail: (id: string) => ['guests', 'detail', id] as const,
  stays: (id: string, page: number) => ['guests', 'detail', id, 'stays', page] as const,
  documents: (id: string) => ['guests', 'detail', id, 'documents'] as const,
  duplicates: (id: string) => ['guests', 'detail', id, 'duplicates'] as const,
}

const BASE = '/guests/guests/'

// ---- Queries ------------------------------------------------------------------------------------

export function useGuests(params: GuestListParams) {
  return useQuery({
    queryKey: guestKeys.list(params),
    queryFn: ({ signal }) => api.get<Page<GuestSummary>>(BASE, { params, signal }),
    placeholderData: keepPreviousData,
  })
}

/** Quick search for pickers (8 best matches); disabled for empty queries. */
export function useGuestSearch(q: string) {
  const query = q.trim()
  return useQuery({
    queryKey: guestKeys.search(query),
    queryFn: ({ signal }) => api.get<Page<GuestSummary>>(BASE, { params: { q: query, page_size: 8 }, signal }),
    enabled: query.length > 0,
    placeholderData: keepPreviousData,
  })
}

const LOOKUP_FIELDS = [
  'first_name',
  'last_name',
  'email',
  'phone',
  'document_type',
  'document_number',
  'nationality',
  'country_of_residence',
] as const

/** Existing guests that look like unsaved data (runs once there is an email, phone or document). */
export function useGuestLookup(input: Partial<GuestInput> | null) {
  const params: Record<string, string> = {}
  for (const field of LOOKUP_FIELDS) {
    const value = input?.[field]
    if (typeof value === 'string' && value.trim()) params[field] = value.trim()
  }
  const hasIdentifier = Boolean(params.email || params.phone || params.document_number)
  return useQuery({
    queryKey: guestKeys.lookup(params),
    queryFn: ({ signal }) => api.get<DuplicateGuest[]>(`${BASE}lookup/`, { params, signal }),
    enabled: hasIdentifier,
  })
}

export function useGuestTags() {
  return useQuery({ queryKey: guestKeys.tags(), queryFn: () => api.get<string[]>(`${BASE}tags/`), staleTime: 60_000 })
}

export function useGuest(id: string) {
  return useQuery({ queryKey: guestKeys.detail(id), queryFn: () => api.get<Guest>(`${BASE}${id}/`) })
}

export function useGuestStays(id: string, page: number) {
  return useQuery({
    queryKey: guestKeys.stays(id, page),
    queryFn: () => api.get<Page<GuestStay>>(`${BASE}${id}/stays/`, { params: { page } }),
    placeholderData: keepPreviousData,
  })
}

export function useGuestDocuments(id: string) {
  return useQuery({ queryKey: guestKeys.documents(id), queryFn: () => api.get<GuestDocument[]>(`${BASE}${id}/documents/`) })
}

export function useGuestDuplicates(id: string, enabled = true) {
  return useQuery({
    queryKey: guestKeys.duplicates(id),
    queryFn: () => api.get<DuplicateGuest[]>(`${BASE}${id}/duplicates/`),
    enabled,
  })
}

// ---- Mutations ----------------------------------------------------------------------------------

function useInvalidateGuests() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: guestKeys.all })
}

export function useCreateGuest() {
  const invalidate = useInvalidateGuests()
  return useMutation({
    mutationFn: (payload: GuestPayload) => api.post<Guest>(BASE, payload),
    onSuccess: () => invalidate(),
  })
}

export function useUpdateGuest(id: string) {
  const queryClient = useQueryClient()
  const invalidate = useInvalidateGuests()
  return useMutation({
    mutationFn: (payload: GuestPayload) => api.patch<Guest>(`${BASE}${id}/`, payload),
    onSuccess: (guest) => {
      queryClient.setQueryData(guestKeys.detail(id), guest)
      void invalidate()
    },
  })
}

export function useUploadDocument(guestId: string) {
  const invalidate = useInvalidateGuests()
  return useMutation({
    mutationFn: ({ kind, file }: { kind: DocumentKind; file: File }) => {
      const formData = new FormData()
      formData.append('kind', kind)
      formData.append('file', file)
      return api.post<GuestDocument>(`${BASE}${guestId}/documents/`, undefined, { formData })
    },
    onSuccess: () => invalidate(),
  })
}

export function useDeleteDocument() {
  const invalidate = useInvalidateGuests()
  return useMutation({
    mutationFn: (documentId: string) => api.delete<void>(`/guests/documents/${documentId}/`),
    onSuccess: () => invalidate(),
  })
}

export function useMergeGuests() {
  const invalidate = useInvalidateGuests()
  return useMutation({
    mutationFn: ({ primaryId, duplicateId }: { primaryId: string; duplicateId: string }) =>
      api.post<Guest>(`${BASE}merge/`, { primary_id: primaryId, duplicate_id: duplicateId, confirm: true }),
    onSuccess: () => invalidate(),
  })
}

export function useAnonymizeGuest(id: string) {
  const queryClient = useQueryClient()
  const invalidate = useInvalidateGuests()
  return useMutation({
    mutationFn: () => api.post<Guest>(`${BASE}${id}/anonymize/`, { confirm: true }),
    onSuccess: (guest) => {
      queryClient.setQueryData(guestKeys.detail(id), guest)
      void invalidate()
    },
  })
}

export function useDeleteGuest() {
  const invalidate = useInvalidateGuests()
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`${BASE}${id}/`),
    onSuccess: () => invalidate(),
  })
}

// ---- Files --------------------------------------------------------------------------------------

/** `file_url` from the API (`/api/v1/...`) → path for the `api` client (which adds `/api/v1`). */
export function apiPath(url: string): string {
  return url.replace(/^\/api\/v1(?=\/)/, '')
}

/** Downloads a private file with the session and `X-Property-Id` (plain links cannot send the header). */
export function fetchPrivateFile(url: string, signal?: AbortSignal): Promise<Blob> {
  return api.get<Blob>(apiPath(url), { responseType: 'blob', signal })
}

export function saveBlob(blob: Blob, filename: string): void {
  const href = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = href
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(href), 1000)
}

export async function downloadGuestExport(guest: Pick<Guest, 'id'>): Promise<void> {
  const blob = await api.get<Blob>(`${BASE}${guest.id}/export/`, { responseType: 'blob' })
  saveBlob(blob, `huesped-${guest.id}.json`)
}
