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
  /** Order in the sidebar; screens that share a number keep registry order. */
  navOrder: number | null
}

export type ScreenId =
  | 'queue'
  | 'escalations'
  | 'intake'
  | 'review'
  | 'pricing'
  | 'staff'
  | 'settings'
  | 'notifications'
  | 'profile'

const ALL: UserRole[] = ['underwriter', 'medical_professional', 'admin']

export const SCREENS: Record<ScreenId, Screen> = {
  queue: {
    id: 'queue',
    path: '/queue',
    label: 'Applications',
    title: 'Applications',
    description: (role) =>
      role === 'medical_professional'
        ? 'Every application your company has taken, newest first. The ones waiting for a medical decision are marked; Escalations shows just those.'
        : role === 'admin'
          ? 'Every application your company has taken, newest first. Open any of them to see where it stands.'
          : 'Every application your company has taken, newest first. Open one to see what the evidence says and record a decision.',
    roles: ALL,
    navOrder: 10,
  },
  escalations: {
    id: 'escalations',
    path: '/escalations',
    label: 'Escalations',
    title: 'Escalations',
    description:
      'Applications an underwriter has passed up because the models found elevated risk. They wait here for a medical professional to decide.',
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
    roles: ALL,
    navOrder: 20,
  },
  review: {
    id: 'review',
    path: '/applications/:id',
    label: 'Application',
    title: 'Application',
    description:
      'What the evidence says, and the decision that is yours to make. The score is advice; the decision is recorded under your name.',
    roles: ALL,
    navOrder: null,
  },
  staff: {
    id: 'staff',
    path: '/admin/users',
    label: 'Staff',
    title: 'Staff',
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
      "What each risk tier is offered and what it costs at the cover a client asks for, under your company's boundaries and rates. Nothing here is issued on its own; a person records every decision.",
    roles: ALL,
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
    .filter((s) => s.navOrder !== null && s.roles.includes(role))
    .sort((a, b) => (a.navOrder ?? 0) - (b.navOrder ?? 0))
}

export function describe(screen: Screen, role: UserRole): string {
  return typeof screen.description === 'function' ? screen.description(role) : screen.description
}
