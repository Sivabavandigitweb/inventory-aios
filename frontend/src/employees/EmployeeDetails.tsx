import type { Employee, EmployeeDirectoryProvider } from './types'

type Props = { employee: Employee; provider: EmployeeDirectoryProvider }

function optionName(options: readonly { id: string; name: string }[], id: string | null) {
  return options.find((option) => option.id === id)?.name ?? 'Not recorded'
}

export function EmployeeDetails({ employee, provider }: Props) {
  const fullName = employee.first_name + ' ' + employee.last_name
  const status = provider.statuses.find((item) => item.value === employee.status)?.label ?? employee.status

  return (
    <div className="employee-details">
      <p className="employee-help">Fictional preview profile. No live employee information is shown.</p>
      <dl className="employee-details-grid">
        <div><dt>Employee code</dt><dd>{employee.employee_number}</dd></div>
        <div><dt>Name</dt><dd>{fullName}</dd></div>
        <div><dt>Department</dt><dd>{optionName(provider.departments, employee.department_id)}</dd></div>
        <div><dt>Team</dt><dd>{optionName(provider.teams, employee.team_id)}</dd></div>
        <div><dt>Designation</dt><dd>{optionName(provider.designations, employee.designation_id)}</dd></div>
        <div><dt>Employment status</dt><dd>{status}</dd></div>
        <div><dt>Joining date</dt><dd>{employee.joining_date ?? 'Not recorded'}</dd></div>
      </dl>
      <div className="employee-future">
        <h3>Allocated assets</h3><p>Unavailable. Allocation records are not connected.</p><a className="employee-preview-link" href={'/allocations?employee=' + encodeURIComponent(employee.employee_number)}>View fictional allocation examples</a>
        <h3>Allocation and return history</h3><p>Planned. No operational history is shown.</p>
        <h3>Employee change history</h3><p>Planned. Organizational changes are not connected.</p>
        <h3>Exit and clearance</h3><p>Inventory clearance is a separate local review and does not establish employment departure.</p><a className="employee-preview-link" href={'/exit-clearance?employee=' + encodeURIComponent(employee.employee_number)}>View fictional clearance examples</a>
      </div>
    </div>
  )
}
