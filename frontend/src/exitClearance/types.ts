/** Fictional review fixtures; no operational exit-case API exists. */
export type ExitClearancePreviewCase = { reference: string; employeeId: string }
export type ExitClearancePreviewData = { cases: ExitClearancePreviewCase[] }
export type ExitClearancePreviewProvider = { load(): Promise<ExitClearancePreviewData> }
