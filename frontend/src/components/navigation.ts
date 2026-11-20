export type NavigationItem = {
  label: string
  to: string
  icon: string
}

export const navigationItems: NavigationItem[] = [
  { label: 'Dashboard', to: '/dashboard', icon: '⌂' },
  { label: 'Assets', to: '/assets', icon: '▣' },
  { label: 'Employees', to: '/employees', icon: '◎' },
  { label: 'Allocations', to: '/allocations', icon: '↗' },
  { label: 'Returns', to: '/returns', icon: '↙' },
  { label: 'Repairs', to: '/repairs', icon: '✣' },
  { label: 'Approvals', to: '/approvals', icon: '✓' },
  { label: 'Reports', to: '/reports', icon: '▤' },
  { label: 'Settings', to: '/settings', icon: '⚙' },
]