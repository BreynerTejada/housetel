import type { ComponentType } from 'react'
import type { RouteObject } from 'react-router'
import { getFeatureRoutes, splitSettingsRoutes } from '@/app/extensions'
import { BareLayout } from '@/app/layouts/BareLayout'
import { PublicLayout } from '@/app/layouts/PublicLayout'
import { NotFound } from '@/app/pages/NotFound'
import { RouteError } from '@/app/pages/RouteError'
import { LoadingState } from '@/components/LoadingState'
import { RequireAuth, RequirePlatformAdmin } from '@/lib/auth'

/** Route-level code splitting: `lazy: page(() => import('./X'), (m) => m.X)`. */
function page<M>(load: () => Promise<M>, pick: (module: M) => ComponentType) {
  return async () => ({ Component: pick(await load()) })
}

/**
 * The whole route tree, assembled from the features' `routes.tsx` (plan §E):
 * public (+ /login) · bare · /app (auth + staff shell, settings/* nested) · /admin (platform admins) · 404.
 * Staff and platform shells load lazily, so marketplace visitors never download them. Errors inside
 * /app and /admin render in the shell's outlet so navigation stays usable.
 */
export function buildRoutes(): RouteObject[] {
  const feature = getFeatureRoutes()
  const { main, settings } = splitSettingsRoutes(feature.app)

  return [
    {
      errorElement: <RouteError />,
      hydrateFallbackElement: <LoadingState className="min-h-dvh" />,
      children: [
        {
          element: <PublicLayout />,
          children: [
            ...feature.public,
            { path: '/login', lazy: page(() => import('@/app/pages/LoginPage'), (m) => m.LoginPage) },
            { path: '*', element: <NotFound home="/" /> },
          ],
        },
        { element: <BareLayout />, children: feature.bare },
        {
          path: '/app',
          element: <RequireAuth />,
          children: [
            {
              lazy: page(() => import('@/app/layouts/AppLayout'), (m) => m.AppLayout),
              children: [
                {
                  errorElement: <RouteError home="/app" />,
                  children: [
                    ...main,
                    {
                      path: 'settings',
                      lazy: page(() => import('@/app/layouts/SettingsLayout'), (m) => m.SettingsLayout),
                      children: [
                        { index: true, lazy: page(() => import('@/app/pages/SettingsIndex'), (m) => m.SettingsIndex) },
                        ...settings,
                      ],
                    },
                    { path: '*', element: <NotFound home="/app" /> },
                  ],
                },
              ],
            },
          ],
        },
        {
          path: '/admin',
          element: <RequirePlatformAdmin />,
          children: [
            {
              lazy: page(() => import('@/app/layouts/AdminLayout'), (m) => m.AdminLayout),
              children: [
                {
                  errorElement: <RouteError home="/admin" />,
                  children: [...feature.admin, { path: '*', element: <NotFound home="/admin" /> }],
                },
              ],
            },
          ],
        },
      ],
    },
  ]
}
