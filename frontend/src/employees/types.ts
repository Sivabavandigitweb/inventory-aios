/** Mirrors the current EmployeeRead and EmployeePage response fields. */
export type Employee = {
  id: string
  employee_number: string
  first_name: string
  last_name: string
  department_id: string | null
  team_id: string | null
  designation_id: string | null
  joining_date: string | null
  status: string
}

export type EmployeePageResult = {
  items: Employee[]
  total: number
  limit: number
  offset: number
}

export type EmployeeFilters = {
  q?: string
  department_id?: string
  status?: string
  limit: number
  offset: number
}

export type EmployeeSummary = { total: number; active: number; inactive: number; departments: number }

export type OrganizationOption = { id: string; name: string; department_id?: string }

export type EmployeeDirectoryProvider = {
  mode: 'fictional-mock'
  listEmployees(filters: EmployeeFilters): Promise<EmployeePageResult>
  getSummary(): Promise<EmployeeSummary>
  statuses: readonly { value: string; label: string }[]
  departments: readonly OrganizationOption[]
  teams: readonly OrganizationOption[]
  designations: readonly OrganizationOption[]
}
