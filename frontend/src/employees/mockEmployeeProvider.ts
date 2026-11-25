import type { Employee, EmployeeDirectoryProvider, EmployeeFilters, OrganizationOption } from './types'

const departments: OrganizationOption[] = [
  { id: '20000000-0000-4000-8000-000000000001', name: 'Technology' },
  { id: '20000000-0000-4000-8000-000000000002', name: 'Operations' },
  { id: '20000000-0000-4000-8000-000000000003', name: 'Finance' },
]

const teams: OrganizationOption[] = [
  { id: '30000000-0000-4000-8000-000000000001', name: 'Support', department_id: departments[0].id },
  { id: '30000000-0000-4000-8000-000000000002', name: 'Systems', department_id: departments[0].id },
  { id: '30000000-0000-4000-8000-000000000003', name: 'Field Services', department_id: departments[1].id },
  { id: '30000000-0000-4000-8000-000000000004', name: 'Facilities', department_id: departments[1].id },
  { id: '30000000-0000-4000-8000-000000000005', name: 'Accounts', department_id: departments[2].id },
]

const designations: OrganizationOption[] = [
  { id: '40000000-0000-4000-8000-000000000001', name: 'Coordinator' },
  { id: '40000000-0000-4000-8000-000000000002', name: 'Specialist' },
  { id: '40000000-0000-4000-8000-000000000003', name: 'Analyst' },
]

function demoEmployee(
  number: number, first_name: string, last_name: string,
  department: number, team: number, designation: number, status: 'active' | 'inactive',
): Employee {
  return {
    id: '10000000-0000-4000-8000-' + String(number).padStart(12, '0'),
    employee_number: 'DEMO-' + String(number).padStart(3, '0'),
    first_name,
    last_name,
    department_id: departments[department].id,
    team_id: teams[team].id,
    designation_id: designations[designation].id,
    joining_date: '2025-01-' + String(number + 3).padStart(2, '0'),
    status,
  }
}

/** Deliberately fictional, local preview records. No fetch or backend fallback. */
const employees: Employee[] = [
  demoEmployee(1, 'Mira', 'Vale', 0, 0, 1, 'active'),
  demoEmployee(2, 'Noah', 'Reed', 0, 1, 2, 'active'),
  demoEmployee(3, 'Asha', 'Quinn', 1, 2, 0, 'active'),
  demoEmployee(4, 'Leo', 'Marsh', 1, 3, 1, 'inactive'),
  demoEmployee(5, 'Nila', 'Stone', 2, 4, 2, 'active'),
  demoEmployee(6, 'Owen', 'Brook', 0, 0, 0, 'active'),
  demoEmployee(7, 'Tara', 'Field', 1, 2, 1, 'active'),
  demoEmployee(8, 'Ilan', 'Wells', 0, 1, 1, 'inactive'),
  demoEmployee(9, 'Rhea', 'Park', 2, 4, 0, 'active'),
  demoEmployee(10, 'Arun', 'Hale', 1, 3, 2, 'active'),
  demoEmployee(11, 'Lina', 'Cove', 0, 0, 2, 'active'),
  demoEmployee(12, 'Theo', 'Pike', 1, 2, 0, 'inactive'),
]

export const mockEmployeeProvider: EmployeeDirectoryProvider = {
  mode: 'fictional-mock',
  departments,
  teams,
  designations,
  // The backend defaults to active; R-07 permits Inactive on exit. No other code is assumed.
  statuses: [
    { value: 'active', label: 'Active' },
    { value: 'inactive', label: 'Inactive' },
  ],
  async getSummary() {
    return {
      total: employees.length,
      active: employees.filter((employee) => employee.status === 'active').length,
      inactive: employees.filter((employee) => employee.status === 'inactive').length,
      departments: new Set(employees.map((employee) => employee.department_id).filter(Boolean)).size,
    }
  },
  async listEmployees(filters: EmployeeFilters) {
    const query = filters.q?.trim().toLocaleLowerCase() ?? ''
    const matching = employees.filter((employee) => {
      const department = departments.find((item) => item.id === employee.department_id)?.name ?? ''
      const team = teams.find((item) => item.id === employee.team_id)?.name ?? ''
      const searchable = [
        employee.employee_number, employee.first_name, employee.last_name,
        employee.first_name + ' ' + employee.last_name, department, team,
      ].join(' ').toLocaleLowerCase()
      return (!query || searchable.includes(query))
        && (!filters.department_id || employee.department_id === filters.department_id)
        && (!filters.status || employee.status === filters.status)
    })
    return {
      items: matching.slice(filters.offset, filters.offset + filters.limit),
      total: matching.length,
      limit: filters.limit,
      offset: filters.offset,
    }
  },
}
