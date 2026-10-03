import type { UserRole } from './types/auth'

/**
 * Every screen in the console, in one place.
 *
 * The sidebar label, the page title and the one-line explanation under it all
 * come from here, so they cannot disagree, and a screen cannot exist without
 * saying what it is for. The description is written for the person using it:
 * plain words, what the screen does, what happens next.
 *
 * `roles` is who sees it in the sidebar and who may open it; App.tsx guards the
 * two role-specific routes with the same list.
 */
export interface Screen {
  id: ScreenId
  path: string
  /** Sidebar label. Short. */
  label: string
  /** Page title. Usually the label; may be longer. */
  title: string
  /** One line under the title. What this screen is for, in plain words. */
  description: string | ((role: UserRole) => string)
  roles: UserRole[]
  /**
   * Roles that see the screen in the sidebar with a lock but cannot open it:
   * it exists, and it is the company owner's. Opening it says so.
   */
  locked?: UserRole[]
  /** Order in the sidebar; screens that share a number keep registry order. */
  navOrder: number | null
}

export type ScreenId =
  | 'queue'
  | 'clients'
  | 'client'
  | 'analytics'
  | 'escalations'
  | 'intake'
  | 'review'
  | 'pricing'
  | 'staff'
  | 'settings'
  | 'notifications'
  | 'profile'
  | 'access'
  | 'bench'

const ALL: UserRole[] = ['underwriter', 'medical_professional', 'admin']
// Taking and deciding applications are not a doctor's: a doctor reviews the
// results of what is sent to them.
const STAFF: UserRole[] = ['underwriter', 'admin']
// The company's book and its prices are the owner's. An underwriter sees that
// they exist, with a lock; a doctor does not see them at all.
const OWNER: UserRole[] = ['admin']

export const SCREENS: Record<ScreenId, Screen> = {
  queue: {
    id: 'queue',
    path: '/queue',
    label: 'Applications',
    title: 'Applications',
    description: (role) =>
      role === 'medical_professional'
        ? 'Every application your company has taken, newest first. The ones waiting for a medical decision are marked; Doctor reviews shows just those.'
        : role === 'admin'
          ? 'Every application your company has taken, newest first. Open any of them to see where it stands.'
          : 'Every application your company has taken, newest first. Open one to see what the evidence says and record a decision.',
    roles: STAFF,
    navOrder: 10,
  },
  clients: {
    id: 'clients',
    path: '/clients',
    label: 'Clients',
    title: 'Clients',
    description:
      'Everyone who has applied through your company, with where their latest application stands and their portal sign-in. A doctor sees only the people sent to them.',
    roles: ALL,
    navOrder: 12,
  },
  client: {
    id: 'client',
    path: '/clients/:id',
    label: 'Client',
    title: 'Client',
    description:
      'Who the client is, what they applied for, and what each of their tests found.',
    roles: ALL,
    navOrder: null,
  },
  analytics: {
    id: 'analytics',
    path: '/analytics',
    label: 'Analytics',
    title: 'Analytics',
    description:
      "The shape of your company's book: what has been asked for, what was approved, what it earns, and how the readers are performing. Every figure comes from real applications.",
    roles: OWNER,
    locked: ['underwriter'],
    navOrder: 14,
  },
  escalations: {
    id: 'escalations',
    path: '/escalations',
    label: 'Doctor reviews',
    title: 'Doctor reviews',
    description:
      'Applications an underwriter has sent to a doctor because the models found elevated risk. They wait here for a doctor to check the results and send them back.',
    roles: ['medical_professional', 'admin'],
    navOrder: 5,
  },
  intake: {
    id: 'intake',
    path: '/applications/new',
    label: 'New application',
    title: 'New application',
    description:
      "Enter the client's details, attach their evidence and confirm what each file is. The models read it after you submit; nothing is decided here.",
    roles: STAFF,
    navOrder: 20,
  },
  review: {
    id: 'review',
    path: '/applications/:id',
    label: 'Application',
    title: 'Application',
    description: (role) =>
      role === 'medical_professional'
        ? 'What the evidence says. Check the results, send them back to the underwriter as correct or wrong, and write to the client if something cannot wait.'
        : 'What the evidence says, and the decision that is yours to make. The score is advice; the decision is recorded under your name.',
    roles: ALL,
    navOrder: null,
  },
  staff: {
    id: 'staff',
    path: '/admin/users',
    label: 'Team',
    title: 'Team',
    description:
      "Who can sign in to this company's console and what each role may do. Add people here; they sign in with the password you set.",
    roles: ['admin'],
    navOrder: 30,
  },
  settings: {
    id: 'settings',
    path: '/admin/settings',
    label: 'Company settings',
    title: 'Company settings',
    description:
      'Defaults that apply to every application this company takes. Changing one affects new applications, not ones already in progress.',
    roles: ['admin'],
    navOrder: 31,
  },
  pricing: {
    id: 'pricing',
    path: '/pricing',
    label: 'Plans and pricing',
    title: 'Plans and pricing',
    description:
      "What each risk tier is offered and what it costs at the cover a client asks for. Change the rates here; every screen follows. Nothing is issued on its own; a person records every decision.",
    roles: OWNER,
    locked: ['underwriter'],
    navOrder: 40,
  },
  notifications: {
    id: 'notifications',
    path: '/notifications',
    label: 'Notifications',
    title: 'Notifications',
    description: 'Changes on applications your company is handling.',
    roles: ALL,
    navOrder: 50,
  },
  bench: {
    id: 'bench',
    path: '/model-bench',
    label: 'Model test bench',
    title: 'Model test bench',
    description:
      'Run one model on one test and see exactly what it says: the score, the raw output, any heatmap, and how long it took. Nothing is stored and no application is made.',
    roles: OWNER,
    navOrder: 33,
  },
  access: {
    id: 'access',
    path: '/access-requests',
    label: 'Access requests',
    title: 'Access requests',
    description:
      "Underwriters and doctors asking to see a client's personal details, and why. Approve to open that one client to that one person for a day.",
    roles: OWNER,
    navOrder: 32,
  },
  profile: {
    id: 'profile',
    path: '/profile',
    label: 'Your account',
    title: 'Your account',
    description: 'Your details, your password, and what your role lets you do.',
    roles: ALL,
    navOrder: 60,
  },
}

/** The sidebar for one role, in order. */
export function navFor(role: UserRole): Screen[] {
  return Object.values(SCREENS)
    .filter((s) => s.navOrder !== null && (s.roles.includes(role) || isLocked(s, role)))
    .sort((a, b) => (a.navOrder ?? 0) - (b.navOrder ?? 0))
}

export function describe(screen: Screen, role: UserRole): string {
  return typeof screen.description === 'function' ? screen.description(role) : screen.description
}

/** Where a signed-in person starts: a doctor with what was sent to them. */
export const homeFor = (role: UserRole | undefined): string =>
  role === 'medical_professional' ? '/escalations' : '/queue'

/** In the sidebar for this role, but closed to it. */
export const isLocked = (screen: Screen, role: UserRole): boolean =>
  Boolean(screen.locked?.includes(role))
