/**
 * Team data layer: members (memberships), invitations, roles and the permission catalog
 * (backend `/api/v1/accounts/…`, see docs/integration-notes/B3-guests-team.md).
 */
import { useMutation, useQuery, useQueryClient, type Query } from '@tanstack/react-query'
import { api, publicApi } from '@/lib/api'
import { ME_QUERY_KEY, type Me } from '@/lib/auth'
import { useSession } from '@/lib/session'

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface PermissionItem {
  code: string
  label_es: string
  label_en: string
}

export interface PermissionModule {
  code: string
  label_es: string
  label_en: string
  permissions: PermissionItem[]
}

export interface RoleRef {
  id: string
  code: string
  name: string
  is_system: boolean
}

export interface Role extends RoleRef {
  description: string
  /** Codes or fnmatch patterns (`bookings.*`, `*`). */
  permissions: string[]
  members_count: number
  /** The current user may assign it (holds every permission it grants). */
  assignable: boolean
  /** Custom role the current user may edit. */
  editable: boolean
  created_at: string
}

export interface PropertyName {
  id: string
  name: string
}

export interface Member {
  /** Membership id. */
  id: string
  user: { id: string; email: string; full_name: string; phone: string; last_login: string | null }
  role: RoleRef
  all_properties: boolean
  properties: PropertyName[]
  is_active: boolean
  is_owner: boolean
  is_self: boolean
  editable: boolean
  created_at: string
}

export type InvitationStatus = 'pending' | 'expired' | 'accepted'

export interface Invitation {
  id: string
  email: string
  role: RoleRef
  all_properties: boolean
  properties: PropertyName[]
  status: InvitationStatus
  expires_at: string
  invited_by: { id: string; full_name: string; email: string } | null
  created_at: string
  /**
   * The link the invitee opens (can be shared by hand). Only while pending and only if `editable`: whoever
   * opens it can create that account and join with that access.
   */
  invite_url: string | null
  /** The current user may resend or revoke it (its role and hotels fit inside theirs). */
  editable: boolean
  /** In the responses of invite/resend: whether the email went out. */
  email_sent?: boolean
}

export interface PublicInvitation {
  email: string
  organization: { name: string }
  role: { name: string; code: string }
  properties: string[]
  all_properties: boolean
  invited_by: string
  expires_at: string
  status: InvitationStatus
  user_exists: boolean
}

export interface InvitePayload {
  email: string
  role_id: string
  all_properties: boolean
  property_ids: string[]
}

export interface MemberPayload {
  role_id?: string
  all_properties?: boolean
  property_ids?: string[]
  is_active?: boolean
}

export interface RolePayload {
  name?: string
  description?: string
  permissions?: string[]
}

export const teamKeys = {
  all: ['team'] as const,
  members: () => ['team', 'members'] as const,
  invitations: () => ['team', 'invitations'] as const,
  roles: () => ['team', 'roles'] as const,
  catalog: () => ['team', 'catalog'] as const,
}

// ---- Queries ------------------------------------------------------------------------------------

export function useMembers() {
  return useQuery({
    queryKey: teamKeys.members(),
    queryFn: () => api.get<Page<Member>>('/accounts/users/', { params: { page_size: 200 } }),
  })
}

export function useInvitations() {
  return useQuery({ queryKey: teamKeys.invitations(), queryFn: () => api.get<Invitation[]>('/accounts/invitations/') })
}

export function useRoles() {
  return useQuery({ queryKey: teamKeys.roles(), queryFn: () => api.get<Role[]>('/accounts/roles/') })
}

export function usePermissionCatalog() {
  return useQuery({
    queryKey: teamKeys.catalog(),
    queryFn: () => api.get<PermissionModule[]>('/accounts/permissions/'),
    staleTime: 10 * 60_000,
  })
}

export function usePublicInvitation(token: string) {
  return useQuery({
    queryKey: ['invitation', token],
    queryFn: () => publicApi.get<PublicInvitation>(`/accounts/invitations/${encodeURIComponent(token)}/`),
    retry: false,
  })
}

// ---- Mutations ----------------------------------------------------------------------------------

function useInvalidateTeam() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: teamKeys.all })
}

export function useInviteMember() {
  const invalidate = useInvalidateTeam()
  return useMutation({
    mutationFn: (payload: InvitePayload) => api.post<Invitation>('/accounts/users/', payload),
    onSuccess: () => invalidate(),
  })
}

export function useUpdateMember() {
  const invalidate = useInvalidateTeam()
  return useMutation({
    mutationFn: ({ id, ...payload }: MemberPayload & { id: string }) => api.patch<Member>(`/accounts/users/${id}/`, payload),
    onSuccess: () => invalidate(),
  })
}

export function useResendInvitation() {
  const invalidate = useInvalidateTeam()
  return useMutation({
    mutationFn: (id: string) => api.post<Invitation>(`/accounts/invitations/${id}/resend/`),
    onSuccess: () => invalidate(),
  })
}

export function useRevokeInvitation() {
  const invalidate = useInvalidateTeam()
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/accounts/invitations/${id}/`),
    onSuccess: () => invalidate(),
  })
}

export function useCreateRole() {
  const invalidate = useInvalidateTeam()
  return useMutation({
    mutationFn: (payload: RolePayload) => api.post<Role>('/accounts/roles/', payload),
    onSuccess: () => invalidate(),
  })
}

export function useUpdateRole() {
  const invalidate = useInvalidateTeam()
  return useMutation({
    mutationFn: ({ id, ...payload }: RolePayload & { id: string }) => api.patch<Role>(`/accounts/roles/${id}/`, payload),
    onSuccess: () => invalidate(),
  })
}

export function useDeleteRole() {
  const invalidate = useInvalidateTeam()
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/accounts/roles/${id}/`),
    onSuccess: () => invalidate(),
  })
}

export function useDuplicateRole() {
  const invalidate = useInvalidateTeam()
  return useMutation({
    mutationFn: (id: string) => api.post<Role>(`/accounts/roles/${id}/duplicate/`),
    onSuccess: () => invalidate(),
  })
}

/**
 * Accept an invitation: the backend starts the invitee's session. Data cached for whoever was signed in on
 * this device before is dropped (and their active hotel forgotten) before storing the new `Me`.
 */
export function useAcceptInvitation(token: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: { full_name?: string; password: string }) =>
      publicApi.post<Me>(`/accounts/invitations/${encodeURIComponent(token)}/accept/`, payload),
    onSuccess: async (me) => {
      const staleStaffData = (query: Query) => query.queryKey[0] !== ME_QUERY_KEY[0] && query.queryKey[0] !== 'invitation'
      await queryClient.cancelQueries({ predicate: staleStaffData })
      queryClient.removeQueries({ predicate: staleStaffData })
      useSession.getState().setLoggedOut(false)
      useSession.getState().setPropertyId(null)
      queryClient.setQueryData(ME_QUERY_KEY, me)
    },
  })
}
